
from .singleton import Singleton
import sys
from .utils import log_detailed
from .workers import StateMachineWorker, LoggerWorker
import logging
from .managers import DBManager, OPCUAClientManager, AlarmManager
from .tags import CVTEngine, Tag
from .state_machine import Machine, DAQ
from automation.opcua.subscription import DAS
from automation.pages.main import ConfigView
from automation.pages.callbacks import init_callbacks
import dash_bootstrap_components as dbc
from automation.buffer import Buffer
from math import ceil


class PyAutomation(Singleton):
    r"""
    Automation is a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern) class to develop multi threads web application
    for general purposes .

    Usage:

    ```python
    >>> from pyautomation import PyAutomation
    >>> app = PyAutomation()
    ```
    """
    PORTS = 65535
    def __init__(self):

        self.machine = Machine()
        self.machine_manager = self.machine.get_state_machine_manager()
        self.db_manager = DBManager()
        self.cvt = CVTEngine()
        self.opcua_client_manager = OPCUAClientManager()
        self.alarm_manager = AlarmManager()
        self.workers = list()
        self.set_log(level=logging.WARNING)

    def get_tags(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        return self.cvt.get_tags()
    
    def create_tag(self,
            name:str, 
            unit:str, 
            display_unit:str,
            variable:str,
            data_type:str='float', 
            description:str="", 
            display_name:str=None,
            opcua_address:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not display_name:

            display_name = name

        message = self.cvt.set_tag(
            name=name,
            unit=unit,
            display_unit=display_unit,
            variable=variable,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=opcua_address,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band
        )
    
        # CREATE OPCUA SUBSCRIPTION
        if not message:

            if scan_time:
            
                self.das.buffer[name] = {
                    "timestamp": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                    "values": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                    "unit": display_unit
                }

            else:

                self.das.buffer[name] = {
                    "timestamp": Buffer(),
                    "values": Buffer(),
                    "unit": display_unit
                }
            
            self.subscribe_opcua(tag=self.cvt.get_tag_by_name(name=name), opcua_address=opcua_address, node_namespace=node_namespace, scan_time=scan_time)

        return message

    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        tag_name = tag.get_name()
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag_name)
        if alarm:

            return f"Tag {tag_name} has an alarm associated"
        
        self.unsubscribe_opcua(tag=tag)
        self.das.buffer.pop(tag_name)
        self.cvt.delete_tag(id=id)
    
    def update_tag(self, id:str, **kwargs):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        self.unsubscribe_opcua(tag)
        result = self.cvt.update_tag(id=id, **kwargs)
        self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=tag.get_scan_time())       
        return result

    def delete_tag_by_name(self, name:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag_by_name(name=name)
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag.get_name())
        if alarm:

            return f"Tag {name} has an alarm associated: {alarm.name}, delete first it"

    def _start_logger(self):
        r"""
        Starts logger in log file
        """
        log_format = "%(asctime)s:%(levelname)s:%(message)s"

        level = self._logging_level
        log_file = self._log_file

        if not log_file:
            logging.basicConfig(level=level, format=log_format)
            return

        logging.basicConfig(filename=log_file, level=level, format=log_format)

    def init_db(self)->LoggerWorker:
        r"""
        Initialize Logger Worker

        **Returns**

        * **db_worker**: (LoggerWorker Object)
        """
        db_worker = LoggerWorker(self.db_manager)
        db_worker.init_database()

        try:

            db_worker.daemon = True
            db_worker.start()

        except Exception as e:
            message = "Error on db worker start-up"
            log_detailed(e, message)

        return db_worker
    
    def find_opcua_servers(self, host:str='127.0.0.1', port:int=4840)->list[dict]:
        r"""
        Documentation here
        """
        result = {
            "message": f"Connection refused to opc.tcp://{host}:{port}"
        }
        try:
            
            server = self.opcua_client_manager.discovery(host=host, port=port)
            result["message"] = f"Successfully connection to {server[0]['DiscoveryUrls'][0]}"
            result["data"] = server
        
        except Exception as err:

            result["data"] = list()
                
        return result

    def get_opcua_clients(self):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.serialize()
    
    def get_opcua_client(self, client_name:str):
        r"""
        Documentation here
        """
        return self.opcua_client_manager.get(client_name=client_name)

    def get_node_values(self, client_name:str, namespaces:list):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_values(client_name=client_name, namespaces=namespaces)
    
    def get_node_attributes(self, client_name:str, namespaces:list):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_attributes(client_name=client_name, namespaces=namespaces)
    
    def get_opcua_tree(self, client_name:str):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_opcua_tree(client_name=client_name)
    
    def add_opcua_client(self, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Documentation here
        """
        servers = self.find_opcua_servers(host=host, port=port)
        
        if servers:
            
            self.opcua_client_manager.add(client_name=client_name, endpoint_url=f"opc.tcp://{host}:{port}")

    def set_log(self, level=logging.INFO, file:str="app.log"):
        r"""
        Sets the log file and level.

        **Parameters:**

        * **level** (str): `logging.LEVEL` (default: logging.INFO).
        * **file** (str): log filename (default: 'app.log').

        **Returns:** `None`

        Usage:

        ```python
        >>> app.set_log(file="app.log")
        ```
        """

        self._logging_level = level

        if file:

            self._log_file = file
        
    def stop_db(self, db_worker:LoggerWorker):
        r"""
        Stops Database Worker
        """
        try:
            db_worker.stop()
        except Exception as e:
            message = "Error on db worker stop"
            log_detailed(e, message)

    def _start_workers(self):
        r"""
        Starts all workers.

        * LoggerWorker
        * AlarmWorker
        * StateMachineWorker
        """
        
        if self._create_tables:

            db_worker = LoggerWorker(self.db_manager)
            self.workers.append(db_worker)

        # if self._create_alarm_worker:
            # alarm_manager = self.get_alarm_manager()
            # alarm_worker = AlarmWorker(alarm_manager)
            # self.workers.append(alarm_worker)

        # StateMachine Worker
        self.machine.start()

    def _stop_workers(self):
        r"""
        Safe stop workers execution
        """
        for worker in self.workers:
            try:
                worker.stop()
            except Exception as e:
                message = "Error on wokers stop"
                log_detailed(e, message)

    def safe_start(self, create_tables:bool=True, alarm_worker:bool=False):
        r"""
        Run the app without a main thread, only run the app with the threads and state machines define
        """
        self._create_tables = create_tables
        self._create_alarm_worker = alarm_worker
        self._start_logger()
        self._start_workers()

    def safe_stop(self):
        r"""
        Stops the app in safe way with the threads
        """
        self._stop_workers()
        logging.info("Manual Shutting down")
        sys.exit()

    def startup_config_page(self, debug:str=False):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".")
        self.dash_app.set_automation_app(self)
        self.das = DAS()
        self.safe_start(create_tables=False)
        init_callbacks(app=self.dash_app)
        self.dash_app.run(debug=debug)

    def subscribe_opcua(self, tag:Tag, opcua_address:str, node_namespace:str, scan_time:float):
        r"""
        Documentation here
        """
        if opcua_address and node_namespace:

            if not scan_time:                                                           # SUBSCRIBE BY DAS

                for client_name, info in self.get_opcua_clients().items():

                    if opcua_address==info["server_url"]:

                        opcua_client = self.get_opcua_client(client_name=client_name)
                        subscription = opcua_client.create_subscription(1000, self.das)
                        node_id = opcua_client.get_node_id_by_namespace(node_namespace)
                        self.das.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)
                        break

            else:                                                                       # SUBSCRIBE BY DAQ

                self.subscribe_tag(tag_name=tag.get_name(), scan_time=scan_time)

    def subscribe_tag(self, tag_name:str, scan_time:float):
        r"""
        Documentatio here
        """
        scan_time = float(scan_time)
        daq = self.machine_manager.get_machine(name=f"DAQ-{scan_time / 1000}")
        tag = self.cvt.get_tag_by_name(name=tag_name)

        if not daq:

            daq = DAQ()
            daq.set_opcua_client_manager(manager=self.opcua_client_manager)
            self.machine.append_machine(machine=daq, interval=scan_time / 1000, mode="async")
            
        daq.subscribe_to(tag=tag)
        self.machine.stop()
        self.machine.start()                

    def unsubscribe_opcua(self, tag:Tag):
        r"""
        Documentation here
        """
        if tag.get_node_namespace():

            for client_name, info in self.get_opcua_clients().items():

                if tag.get_opcua_address()==info["server_url"]:

                    opcua_client = self.get_opcua_client(client_name=client_name)
                    node_id = opcua_client.get_node_id_by_namespace(tag.get_node_namespace())
                    self.das.unsubscribe(client_name=client_name, node_id=node_id)
                    break
    
        self.machine_manager.unsubscribe_tag(tag=tag)
        # CLEAR BUFFER
        scan_time = tag.get_scan_time()
        if scan_time:
            
            self.das.buffer[tag.get_name()].update({
                "timestamp": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                "values": Buffer(size=ceil(10 / ceil(scan_time / 1000)))
            })
        else:
            self.das.buffer[tag.get_name()].update({
                "timestamp": Buffer(),
                "values": Buffer()
            })

    def run(self, debug:bool=False):
        r"""
        Runs main app thread and all defined threads by decorators and State Machines besides this method starts app logger

        **Returns:** `None`

        Usage

        ```python
        >>> app.run()
        ```
        """
        self.startup_config_page(debug=debug)