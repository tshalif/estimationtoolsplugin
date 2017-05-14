import copy, sys
from datetime import timedelta

from genshi.builder import tag
from trac.util.text import unicode_quote, unicode_urlencode, \
                           obfuscate_email_address
from trac.wiki.macros import WikiMacroBase

from estimationtools.utils import parse_options, execute_query, \
                                  get_estimation_suffix, get_closed_states, \
                                  get_serverside_charts, EstimationToolsBase, parse_date

DEFAULT_OPTIONS = {'width': '400', 'height': '100', 'color': 'ff9900', 'workhoursperday': 8}


class WorkloadChart(EstimationToolsBase, WikiMacroBase):
    """Creates workload chart for the selected tickets.

    This macro creates a pie chart that shows the remaining estimated workload per ticket owner,
    and the remaining work days.
    It has the following parameters:
     * a comma-separated list of query parameters for the ticket selection, in the form "key=value" as specified in TracQuery#QueryLanguage.
     * `width`: width of resulting diagram (defaults to 400)
     * `height`: height of resulting diagram (defaults to 100)
     * `color`: color specified as 6-letter string of hexadecimal values in the format `RRGGBB`.
       Defaults to `ff9900`, a nice orange.

    Examples:
    {{{
        [[WorkloadChart(milestone=Sprint 1)]]
        [[WorkloadChart(milestone=Sprint 1, width=600, height=100, color=00ff00)]]
    }}}
    """

    estimation_suffix = get_estimation_suffix()
    closed_states = get_closed_states()
    serverside_charts = get_serverside_charts()

    def expand_macro(self, formatter, name, content):
        req = formatter.req
        db = self.env.get_db_cnx()
        # prepare options
        options, query_args = parse_options(db, content, copy.copy(DEFAULT_OPTIONS))

        query_args[self.estimation_field + "!"] = None
        tickets = execute_query(self.env, req, query_args)

        sum = 0.0
        estimations = {}
        for ticket in tickets:
            if ticket['status'] in self.closed_states:
                continue
            try:
                estimation = float(ticket[self.estimation_field] or 0.0)

                if options.get('remainingworkload'):
                
                    completion_cursor = db.cursor()

                    completion_cursor.execute("SELECT t.value AS totalhours, c.value AS complete, d.value AS due_close FROM ticket tk LEFT JOIN ticket_custom t ON (tk.id = t.ticket AND t.name = 'totalhours') LEFT JOIN ticket_custom c ON (tk.id = c.ticket AND c.name = 'complete') LEFT JOIN ticket_custom d ON (tk.id = d.ticket AND d.name = 'due_close') WHERE tk.id = %s" % ticket['id'])

                    for row in completion_cursor:
                
                        ticket['totalhours'], ticket['complete'], ticket['due_close'] = row
                        break

                    # skip ticket ticket if due date is later than 'enddate':
                    if options.get('showdueonly'):

                        if not ticket['due_close']:
                            continue # skip tickets with empty ETA when in 'showdueonly' mode
                        due_close = parse_date(ticket['due_close'], ["%Y/%m/%d"])
                        startdate = options.get('startdate')
                        enddate = options.get('enddate')

                        if startdate and startdate > due_close:
                            continue # skip tickets with ETA in the past

                        if enddate and enddate < due_close:
                            continue # skip tickets with ETA in the future

                        pass
                    
                    totalhours = float(ticket['totalhours'] or 0.0)

                    completed = (float(ticket['complete'] or 0.0) / 100) * estimation
                    completed_hours = min(estimation, max(totalhours, completed))

                    estimation -= completed_hours

                    pass
                
                owner = ticket['owner']

                sum += estimation
                if estimations.has_key(owner):
                    estimations[owner] += estimation
                else:
                    estimations[owner] = estimation
            except:
                raise

        # Title
        title = 'Workload'

        days_remaining = None
        
        # calculate remaining work time
        if options.get('today') and options.get('enddate'):
            currentdate = options['today']
            day = timedelta(days=1)
            days_remaining = 0
            while currentdate <= options['enddate']:
                if currentdate.weekday() < 5:
                    days_remaining += 1
                currentdate += day
            title += ' %g%s (~%s workdays left)' % (round(sum, 2),
                                    self.estimation_suffix, days_remaining)

        estimations_string = []
        labels = []
        workhoursperday = max(float(options.get('workhoursperday')), 0.0)
        chts = '000000'
        
        for owner, estimation in estimations.iteritems():
            # Note: Unconditional obfuscation of owner in case it represents
            # an email adress, and as the chart API doesn't support SSL
            # (plain http transfer only, from either client or server).
            label = "%s %g%s" % (obfuscate_email_address(owner),
                            round(estimation, 2),
                            self.estimation_suffix)

            if days_remaining != None:

                user_remaining_hours = days_remaining * workhoursperday

                if not user_remaining_hours or (estimation / user_remaining_hours) > 1:
                    label = "%s (~%g hours left)!" % (label, round(user_remaining_hours, 2)) # user does not have enough hours left
                    chts = 'FF0000' # set chart title style to red
                    pass
                pass
                    
            labels.append(label)
            
            estimations_string.append(str(int(estimation)))

            pass
        
        chart_args = unicode_urlencode({'chs': '%sx%s' % (options['width'], options['height']),
                      'chf': 'bg,s,00000000',
                      'chd': 't:%s' % ",".join(estimations_string),
                      'cht': 'p3',
                      'chtt': title,
                      'chts': chts,
                      'chl': "|".join(labels),
                      'chco': options['color']})
        
        self.log.debug("WorkloadChart data: %s" % repr(chart_args))
        if self.serverside_charts:
            return tag.image(src="%s?data=%s" % (req.href.estimationtools('chart'),
                                    unicode_quote(chart_args)),
                             alt="Workload Chart (server)")
        else:
            return tag.image(src="https://chart.googleapis.com/chart?%s" % chart_args,
                             alt="Workload Chart (client)")
