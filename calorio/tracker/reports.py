from datetime import timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from django.core.mail import EmailMessage
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .gamification import compute_stats
from .models import Activity, Goal, Meal


def week_data(user, end=None):
    end = end or timezone.localdate()
    start = end - timedelta(days=6)
    goal, _ = Goal.objects.get_or_create(user=user)

    meal_rows = {
        r['day']: r
        for r in Meal.objects.filter(user=user, eaten_at__date__gte=start, eaten_at__date__lte=end)
        .annotate(day=TruncDate('eaten_at'))
        .values('day')
        .annotate(total_calories=Sum('calories'), total_protein=Sum('protein'))
    }
    step_rows = {
        r['date']: r['total_steps']
        for r in Activity.objects.filter(user=user, date__gte=start, date__lte=end)
        .values('date')
        .annotate(total_steps=Sum('steps'))
    }

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        m = meal_rows.get(d)
        days.append({
            'date': d,
            'logged': m is not None,
            'calories': int(m['total_calories'] or 0) if m else 0,
            'protein': round(float(m['total_protein'] or 0), 1) if m else 0.0,
            'steps': int(step_rows.get(d) or 0),
        })

    logged = [d for d in days if d['logged']]
    n = len(logged)
    return {
        'start': start,
        'end': end,
        'goal': goal,
        'days': days,
        'days_logged': n,
        'avg_calories': round(sum(d['calories'] for d in logged) / n) if n else 0,
        'avg_protein': round(sum(d['protein'] for d in logged) / n, 1) if n else 0,
        'protein_goal_days': sum(1 for d in logged if goal.protein and d['protein'] >= goal.protein),
        'total_steps': sum(d['steps'] for d in days),
        'streak': compute_stats(user)['logging']['current'],
    }


def make_table(rows, header=False, widths=None):
    table = Table(rows, colWidths=widths)
    style = [
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]
    if header:
        style += [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eefc')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ]
    table.setStyle(TableStyle(style))
    return table


def build_pdf(user, data):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title='Calorio weekly report')
    styles = getSampleStyleSheet()
    goal = data['goal']
    days = data['days']

    story = [
        Paragraph('Calorio weekly report', styles['Title']),
        # escape(): Paragraph reads <tags>, so user text must never go in raw
        Paragraph(
            f"{escape(user.username)}: {data['start']:%d %b} to {data['end']:%d %b %Y}",
            styles['Normal'],
        ),
        Spacer(1, 16),
        make_table([
            ['Days logged', f"{data['days_logged']} / 7"],
            ['Average calories (logged days)', f"{data['avg_calories']} (goal {goal.calories})"],
            ['Average protein (logged days)', f"{data['avg_protein']} g (goal {goal.protein} g)"],
            ['Days protein goal met', str(data['protein_goal_days'])],
            ['Total steps', f"{data['total_steps']:,}"],
            ['Current logging streak', f"{data['streak']} days"],
        ], widths=[240, 200]),
        Spacer(1, 20),
        Paragraph(f"Calories per day (goal {goal.calories})", styles['Heading3']),
    ]

    calories = [d['calories'] for d in days]
    chart = VerticalBarChart()
    chart.x, chart.y, chart.width, chart.height = 40, 30, 380, 130
    chart.data = [calories]
    chart.categoryAxis.categoryNames = [f"{d['date']:%a}" for d in days]
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max([goal.calories] + calories) * 1.1
    chart.bars[0].fillColor = colors.HexColor('#4f8cff')
    drawing = Drawing(440, 180)
    drawing.add(chart)
    story += [drawing, Spacer(1, 12), Paragraph('Day by day', styles['Heading3'])]

    rows = [['Date', 'Calories', 'Protein (g)', 'Steps']]
    for d in days:
        rows.append([
            f"{d['date']:%a %d %b}",
            str(d['calories']) if d['logged'] else '-',
            str(d['protein']) if d['logged'] else '-',
            f"{d['steps']:,}",
        ])
    story += [
        make_table(rows, header=True, widths=[130, 100, 100, 100]),
        Spacer(1, 12),
        Paragraph(
            'Calories and protein come from what you logged. AI and restaurant estimates are approximate.',
            styles['Italic'],
        ),
    ]

    doc.build(story)
    return buffer.getvalue()


def send_weekly_report(user):
    data = week_data(user)
    pdf = build_pdf(user, data)
    message = EmailMessage(
        subject=f"Your Calorio week: {data['start']:%d %b} to {data['end']:%d %b}",
        body=(
            f"Hi {user.username},\n\n"
            "Your weekly report is attached.\n"
            f"You logged {data['days_logged']} of 7 days, "
            f"averaging {data['avg_calories']} kcal on those days.\n\n"
            "You get this because weekly reports are turned on in Calorio. "
            "You can turn them off in the app."
        ),
        to=[user.email],
    )
    message.attach(f"calorio-{data['end']}.pdf", pdf, 'application/pdf')
    message.send()