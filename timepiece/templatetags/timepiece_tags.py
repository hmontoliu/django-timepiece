import urllib
import datetime
from decimal import Decimal

from django import template
from django.db.models import Sum

from django.core.urlresolvers import reverse

from dateutil.relativedelta import relativedelta

from timepiece.models import PersonRepeatPeriod, AssignmentAllocation
import timepiece.models as timepiece
from timepiece.utils import get_total_time, get_week_start


register = template.Library()


@register.filter
def seconds_to_hours(seconds):
    return round(seconds / 3600.0, 2)


@register.inclusion_tag('timepiece/time-sheet/bar_graph.html',
                        takes_context=True)
def bar_graph(context, name, worked, total, width=None, suffix=None):
    if not width:
        width = 400
        suffix = 'px'
    left = total - worked
    over = 0
    over_total = 0
    error = ''
    if worked < 0:
        error = 'Somehow you\'ve logged %s negative hours for %s this week.' \
        % (abs(worked), name)
    if left < 0:
        over = abs(left)
        left = 0
        worked = total
        total = over + total
    return {
        'name': name, 'worked': worked,
        'total': total, 'left': left,
        'over': over, 'width': width,
        'suffix': suffix, 'error': error,
        }


@register.inclusion_tag('timepiece/time-sheet/my_ledger.html',
                        takes_context=True)
def my_ledger(context):
    try:
        period = PersonRepeatPeriod.objects.select_related(
            'user',
            'repeat_period',
        ).get(
            user=context['request'].user
        )
    except PersonRepeatPeriod.DoesNotExist:
        return {'period': False}
    return {'period': period}


@register.inclusion_tag('timepiece/time-sheet/_date_filters.html',
    takes_context=True)
def date_filters(context, options):
    request = context['request']
    from_slug = 'from_date'
    to_slug = 'to_date'
    use_range = True
    if not options:
        options = ('months', 'quaters', 'years')

    def construct_url(from_date, to_date):
        url = '%s?%s=%s' % (
            request.path,
            to_slug,
            to_date.strftime('%m/%d/%Y'),
        )
        if use_range:
            url += '&%s=%s' % (
                from_slug,
                from_date.strftime('%m/%d/%Y'),
            )
        return url

    filters = {}
    if 'months_no_range' in options:
        filters['Past 12 Months'] = []
        single_month = relativedelta(months=1)
        from_date = datetime.date.today().replace(day=1) + \
            relativedelta(months=1)
        for x in range(12):
            to_date = from_date
            use_range = False
            from_date = to_date - single_month
            url = construct_url(from_date, to_date - relativedelta(days=1))
            filters['Past 12 Months'].append(
                (from_date.strftime("%b '%y"), url))
        filters['Past 12 Months'].reverse()

    if 'months' in options:
        filters['Past 12 Months'] = []
        single_month = relativedelta(months=1)
        from_date = datetime.date.today().replace(day=1) + \
            relativedelta(months=1)
        for x in range(12):
            to_date = from_date
            from_date = to_date - single_month
            url = construct_url(from_date, to_date - relativedelta(days=1))
            filters['Past 12 Months'].append(
                (from_date.strftime("%b '%y"), url))
        filters['Past 12 Months'].reverse()

    if 'years' in options:
        start = datetime.date.today().year - 3

        filters['Years'] = []
        for year in range(start, start + 3):
            from_date = datetime.datetime(year, 1, 1)
            to_date = from_date + relativedelta(years=1)
            url = construct_url(from_date, to_date - relativedelta(days=1))
            filters['Years'].append((str(from_date.year), url))

    if 'quarters' in options:
        filters['Quarters (Calendar Year)'] = []
        to_date = datetime.date(datetime.date.today().year - 1, 1, 1)
        for x in range(8):
            from_date = to_date
            to_date = from_date + relativedelta(months=3)
            url = construct_url(from_date, to_date - relativedelta(days=1))
            filters['Quarters (Calendar Year)'].append(
                ('Q%s %s' % ((x % 4) + 1, from_date.year), url)
            )

    return {'filters': filters}


@register.simple_tag
def hours_for_assignment(assignment, date):
    end = date + relativedelta(days=5)
    blocks = assignment.blocks.filter(
        date__gte=date, date__lte=end).select_related()
    hours = blocks.aggregate(hours=Sum('hours'))['hours']
    if not hours:
        hours = ''
    return hours


@register.simple_tag
def total_allocated(assignment):
    hours = assignment.blocks.aggregate(hours=Sum('hours'))['hours']
    if not hours:
        hours = ''
    return hours


@register.simple_tag
def hours_for_week(user, date):
    end = date + relativedelta(days=5)
    blocks = AssignmentAllocation.objects.filter(assignment__user=user,
                                                 date__gte=date, date__lte=end)
    hours = blocks.aggregate(hours=Sum('hours'))['hours']
    if not hours:
        hours = ''
    return hours


@register.simple_tag
def weekly_hours_worked(rp, date):
    hours = rp.hours_in_week(date)
    if not hours:
        hours = ''
    return hours


@register.simple_tag
def monthly_overtime(rp, date):
    hours = rp.total_monthly_overtime(date)
    if not hours:
        hours = ''
    return hours


@register.simple_tag
def week_start(date):
    return get_week_start(date).strftime('%m/%d/%Y')


@register.simple_tag
def get_active_hours(entry):
    """Use with active entries to obtain time worked so far"""
    if not entry.end_time:
        if entry.is_paused:
            entry.end_time = entry.pause_time
        else:
            entry.end_time = datetime.datetime.now()
    return Decimal('%.2f' % round(entry.total_hours, 2))


@register.inclusion_tag('timepiece/time-sheet/_project_total_row.html',
                        takes_context=True)
def show_project_hours(context, hours, date_headers, form):
    billable = form.data.get('billable', False)
    non_billable = form.data.get('non_billable', False)
    ordered_hours = []
    for date in date_headers:
        total = hours.get(date, '')
        result = ''
        if total:
            result = 0
            if not billable and not non_billable:
                result += total.get('total', 0)
            if billable:
                result += total.get('billable', 0)
            if non_billable:
                result += total.get('non_billable', 0)
        ordered_hours.append(result)
    return {
        'hours': ordered_hours
    }


@register.inclusion_tag('timepiece/time-sheet/_invoice_row.html',
                        takes_context=True)
def build_invoice_row(context, entries, to_date, from_date):
    hours_invoiced = hours_uninvoiced = 0
    for entry in entries:
        project = entry['project__pk']
        if entry['status'] == 'invoiced':
            hours_invoiced += entry['s']
        else:
            hours_uninvoiced += entry['s']
    to_date_str = from_date_str = ''
    if to_date:
        to_date_str = to_date.strftime('%m/%d/%Y')
    if from_date:
        from_date_str = from_date.strftime('%m/%d/%Y')
    csv_get_str = urllib.urlencode({
        'to_date': to_date_str,
        'from_date': from_date_str,
        'status': 'approved',
    })
    csv_url = reverse('export_project_time_sheet', args=[project, ])
    csv_url += '?' + csv_get_str
    invoice_get_str = urllib.urlencode({
        'to_date': to_date_str,
        'from_date': from_date_str,
        'project': project,
    })
    invoice_url = reverse('time_sheet_change_status', args=['invoice', ])
    invoice_url += '?' + invoice_get_str
    return {
        'hours_invoiced': hours_invoiced,
        'hours_uninvoiced': hours_uninvoiced,
        'csv_url': csv_url,
        'invoice_url': invoice_url,
        }
