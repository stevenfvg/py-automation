import dash
from automation.pages.components import Components


class ConfigView(dash.Dash):
    r"""
    Documentation here
    """

    def __init__(self, **kwargs):
    
        super(ConfigView, self).__init__(__name__, suppress_callback_exceptions=True, **kwargs)
        
        self.layout = dash.html.Div([
            dash.dcc.Interval(id='timestamp-interval', interval=1000, n_intervals=0),
            Components.navbar(),
            dash.page_container
        ])

    def set_automation_app(self, automation_app):

        self.automation = automation_app
        
    def tags_table_data(self):
        
        return self.automation.cvt.get_tags()
    
    def alarms_table_data(self):

        return [{
                "id": alarm["id"],
                "tag": alarm["tag"], 
                "name": alarm["name"],
                "description": alarm["description"],
                "state": alarm["state"],
                "type": alarm["type"],
                "trigger_value": alarm["trigger_value"],
                "operations": ""
                } for alarm in self.automation.alarm_manager.serialize()]
    
    def machines_table_data(self):

        return self.automation.serialize_machines()