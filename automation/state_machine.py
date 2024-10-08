import logging, queue
from datetime import datetime
from statemachine import State, StateMachine
from .workers.state_machine import StateMachineWorker
from .managers.state_machine import StateMachineManager
from .managers.opcua_client import OPCUAClientManager
from .singleton import Singleton
from .buffer import Buffer
from .models import StringType, IntegerType, FloatType, BooleanType, ProcessType
from .tags.cvt import CVTEngine, Tag
from .tags.tag import MachineObserver
from .opcua.subscription import DAS
from .modules.users.users import User
from .utils.decorators import set_event, validate_types, logging_error_handler
from .variables import (
    Temperature,
    Length,
    Current,
    Time,
    Pressure,
    Mass,
    Force,
    Power,
    VolumetricFlow)
from .logger.machines import MachinesLoggerEngine



class Machine(Singleton):
    r"""Documentation here
    """
    def __init__(self):

        self.machine_manager = StateMachineManager()
        self.machines_engine = MachinesLoggerEngine()
        self.state_worker = None

    def append_machine(self, machine:StateMachine, interval:FloatType=FloatType(1), mode:str='async'):
        r"""
        Append a state machine to the state machine manager.

        **Parameters:**

        * **machine** (`PyHadesStateMachine`): a state machine object.
        * **interval** (int): Interval execution time in seconds.
        """
        if isinstance(machine, DAQ):
            
            machine.name = StringType(f"DAQ-{interval.value}")
        
        machine.set_interval(interval)
        self.machine_manager.append_machine((machine, interval, mode))
        self.machines_engine.create(
            name=machine.name.value,
            interval=interval.value,
            description=machine.description.value,
            classification=machine.classification.value,
            buffer_size=machine.buffer_size.value,
            buffer_roll_type=machine.buffer_roll_type.value,
            criticity=machine.criticity.value,
            priority=machine.priority.value
        )

    def drop(self, name:str):
        r"""
        Documentation here
        """
        self.machine_manager.drop(name=name)

    def get_machine(self, name:str):
        r"""
        Returns a PyHades State Machine defined by its name.

        **Parameters:**

        * **name** (str): a pyhades state machine name.

        Usage

        ```python
        >>> state_machine = app.get_machine('state_machine_name')
        ```
        """

        return self.machine_manager.get_machine(name)

    def get_machines(self)->list:
        r"""
        Returns all defined PyHades state machines.

        **Returns** (list)

        Usage

        ```python
        >>> state_machines = app.get_machines()
        ```
        """

        return self.machine_manager.get_machines()

    def get_state_machine_manager(self)->StateMachineManager:
        r"""
        Gets state machine Manager

        **Returns:** StateMachineManager instance

        ```python
        >>> state_manager = app.get_state_machine_manager()
        ```
        """
        return self.machine_manager

    def start(self, machines:tuple=None):
        r"""
        Starts statemachine worker
        """
        # StateMachine Worker
        config = self.load_db_machines_config()

        if config:

            if machines:

                for machine in machines:

                    if machine.name.value in config:

                        machine.description.value = config[machine.name.value]["description"]
                        machine.classification.value = config[machine.name.value]["classification"]
                        machine.buffer_size.value = config[machine.name.value]["buffer_size"]
                        machine.buffer_roll_type.value = config[machine.name.value]["buffer_roll_type"]
                        machine.criticity.value = config[machine.name.value]["criticity"]
                        machine.priority.value = config[machine.name.value]["priority"]
                        self.append_machine(machine=machine, interval=FloatType(config[machine.name.value]["interval"]))

        else:

            if machines:
                
                for machine in machines:

                    self.append_machine(machine=machine)

        state_manager = self.get_state_machine_manager()
        
        if state_manager.exist_machines():
            
            self.state_worker = StateMachineWorker(state_manager)
            self.state_worker.daemon = True
            self.state_worker.start()

    def load_db_machines_config(self):

        return self.machines_engine.read_config()

    def join(self, machine):

        self.state_worker._async_scheduler.join(machine)

    def stop(self):
        r"""
        Safe stop workers execution
        """
        try:
            self.state_worker.stop()

        except Exception as e:
            message = f"Error on wokers stop, {e}"
            logging.error(message)


class StateMachineCore(StateMachine):

    starting = State('start', initial=True)
    waiting = State('wait')
    running = State('run')
    restarting = State("restart")
    resetting = State('reset')

    # Transitions
    start_to_wait = starting.to(waiting)
    wait_to_run = waiting.to(running)
    run_to_reset = running.to(resetting)
    reset_to_start = resetting.to(starting)
    run_to_restart = running.to(restarting)
    restart_to_wait = restarting.to(waiting)
    wait_to_reset = waiting.to(resetting)
    wait_to_restart = waiting.to(restarting)

    def __init__(
            self,
            name:str,
            description:str="",
            classification:str=""
        ):
        self.criticity = IntegerType(default=2)
        self.priority = IntegerType(default=1)
        self.description = StringType(default=description)
        self.classification = StringType(default=classification)
        self.name = StringType(default=name)
        self.machine_interval = FloatType(default=1.0)
        self.buffer_size = IntegerType(default=10)
        self.buffer_roll_type = StringType(default='backward')
        self.__subscribed_to = dict()
        self.restart_buffer()
        transitions = []
        for state in self.states:
            transitions.extend(state.transitions)
        self.transitions = transitions
        self.machine_engine = MachinesLoggerEngine()
        super(StateMachineCore, self).__init__()

    # State Methods
    def while_starting(self):
        r"""
        This method is executed every machine loop when it is on Start state

        Configure your state machine here
        """
        # DEFINE DATA BUFFER
        self.set_buffer_size(size=self.buffer_size.value)
        # TRANSITION
        self.send('start_to_wait')

    def while_waiting(self):
        r"""
        This method is executed every machine loop when it is on Wait state

        It was designed to check your buffer data in self.data, if your buffer is full, so they pass to run state
        """
        ready_to_run = True
        for _, value in self.data.items():

            if len(value) < value.max_length:
                ready_to_run=False
                break

        if ready_to_run:

            self.send('wait_to_run')

    def while_running(self):
        r"""
        This method is executed every machine loop when it is on Run state

        Depending on you state machine goal, write your script here
        """
        self.criticity.value = 1

    def while_resetting(self):
        r"""
        This method is executed every machine loop when it is on Reset state
        """
        self.send("reset_to_start")

    def while_restarting(self):
        r"""
        This method is executed every machine loop when it is on Restart state
        """
        self.restart_buffer()
        self.send("restart_to_wait")

    # Auxiliaries Methods   
    def put_attr(self, attr_name:str, value:StringType|FloatType|IntegerType|BooleanType, user:User=None):
        
        attr = getattr(self, attr_name)
        attr.set_value(value=value, user=user, name=attr_name)
        kwargs = {
            f"{attr_name}": value
        }
        self.machine_engine.put(name=self.name, **kwargs)

    def add_process_variable(self, name:str, tag:Tag, read_only:bool=False):
        r"""
        Documentation here
        """
        
        props = self.__dict__
        if name not in props.items():
            process_variable = ProcessType(tag=Tag, default=tag.value, read_only=read_only)
            setattr(self, name, process_variable)

    def get_process_variables(self):
        r"""
        Documentation here
        """

        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, ProcessType):

                result[key] = value.serialize()

        return result

    def get_process_variable(self, name:str):
        r"""
        Documentation here
        """
        props = self.__dict__
        if name in props.items():

            value = props[name]
            if isinstance(value, ProcessType):

                return value.serialize()

    @validate_types(size=int, output=None)
    def set_buffer_size(self, size:int, user:User=None)->None:
        r"""
        Set data buffer size

        # Parameters

        - *size:* [int] buffer size
        """
        self.buffer_size.value = size
        self.restart_buffer()

    def restart_buffer(self):
        r"""
        Restart Buffer
        """
        self.data = {tag_name: Buffer(size=self.buffer_size.value, roll=self.buffer_roll_type.value) for tag_name, _ in self.get_subscribed_tags().items()}

    @validate_types(output=dict)
    def get_subscribed_tags(self)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return self.__subscribed_to
    
    def subscribe_to(self, tag:Tag):
        r"""

        # Parameters

        - *tags:* [list] 
        """
        tag_name = tag.get_name()
        
        if tag_name not in self.get_subscribed_tags():

            setattr(self, tag_name, ProcessType(tag=tag, default=tag.value, read_only=True))
            self.__subscribed_to[tag.name] = tag
            self.attach(machine=self, tag=tag)
            self.restart_buffer()
            return True

    @validate_types(tag=Tag, output=None|bool)
    def unsubscribe_to(self, tag:Tag):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if tag.name in self.__subscribed_to:
            delattr(self, tag.name)
            self.__subscribed_to.pop(tag.name)
            self.restart_buffer()
            return True

    @validate_types(
            tag=str, 
            value=Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow, 
            timestamp=datetime, 
            output=None)
    def notify(
        self, 
        tag:str, 
        value:Temperature|Length|Current|Time|Pressure|Mass|Force|Power|VolumetricFlow, 
        timestamp:datetime):
        r"""
        This method provide an interface to CVT to notify if tag value has change
        
        # Parameters

        - *tag:* [Tag] tag Object
        - *value:* [int|float|bool] tag value
        """
        if tag in self.get_subscribed_tags():
            _tag = self.__subscribed_to[tag]
            attr = getattr(self, tag)
            value = value.convert(to_unit=_tag.get_display_unit())
            attr.value = value
            # IMPORTANTE A CAMBIAR SEGUN LA UNIDAD QUE NECESITEN LOS MODELOS
            self.data[tag](value)

    @logging_error_handler
    def attach(self, machine, tag:Tag):
        cvt = CVTEngine()
        def attach_observer(machine, tag:Tag):

            observer = MachineObserver(machine)
            query = dict()
            query["action"] = "attach_observer"
            query["parameters"] = {
                "name": tag.name,
                "observer": observer,
            }
            cvt.request(query)
            cvt.response()

        attach_observer(machine, tag)

    @set_event(message=f"Switched", classification="State Machine", priority=2, criticity=3)
    @validate_types(to=str, user=User, output=tuple)
    def transition(self, to:str, user:User=None):
        r"""
        Documentation here
        """
        try:
            _from = self.current_state.name.lower()
            transition_name = f'{_from}_to_{to}'
            allowed_transitions = self._get_active_transitions()
            for _transition in allowed_transitions:
                if f"{_transition.source.name}_to_{_transition.target.name}"==transition_name:
                    self.send(transition_name)
                    return self, f"from: {_from} to: {to}"
                
            return None, f"Transitio to {to} not allowed"
            
        except Exception as err:

            logging.warning(f"Transition from {_from} state to {to} state for {self.name.value} is not allowed")

    @validate_types(output=int|float)
    def get_interval(self)->int|float:
        r"""
        Gets overall state machine interval

        **Returns**

        * **(float)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> interval = machine.get_interval()
        ```
        """
        return self.machine_interval.value

    @validate_types(interval=IntegerType|FloatType, user=User, output=None)
    def set_interval(self, interval:IntegerType|FloatType, user:User=None):
        r"""
        Sets overall machine interval

        **Parameters**

        * **interval:** (float) overal machine interval in seconds

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> machine.set_interval(0.5)
        ```
        """        
        self.machine_interval = interval

    def _get_active_transitions(self):
        r"""
        Gets allowed transitions based on the current state

        **Returns**

        * **(list)**
        """
        result = list()

        current_state = self.current_state
        transitions = self.transitions

        for transition in transitions:

            if transition.source == current_state:

                result.append(transition)

        return result

    def _activate_triggers(self):
        r"""
        Allows to execute the on_ method in transitions when it's necesary
        """
        transitions = self._get_active_transitions()

        for transition in transitions:
            method_name = transition.identifier
            method = getattr(self, method_name)

            try:
                source = transition.source
                if not source._trigger:
                    continue
                if source._trigger.evaluate():
                    method()
            except Exception as e:
                error = str(e)
                logging.error(f"Machine - {self.name.value}:{error}")

    def loop(self):
        r"""
        This method is executed by state machine worker every state machine interval to execute the correct method according its state
        """
        method_name = f"while_{self.current_state.value}"

        if method_name in dir(self):

            method = getattr(self, method_name)
            method()            

    @validate_types(output=list)
    def get_states(self)->list[str]:
        r"""
        Gets a list of state machine's names

        **Returns**

        * **(list)**

        Usage

        ```python
        >>> machine = app.get_machine(name)
        >>> states = machine.get_states()
        ```
        """
        return [state.value for state in self.states]

    @validate_types(output=dict)
    def get_serialized_models(self)->dict:
        r"""
        Gets class attributes defined by [model types]()

        **Returns**

        * **(dict)**
        """
        result = dict()
        props = self.__dict__
        
        for key, value in props.items():

            if isinstance(value, (StringType, FloatType, IntegerType, BooleanType, ProcessType)):

                if isinstance(value, ProcessType):

                    result[key] = value.serialize()

                else:

                    result[key] = value.value

        return result

    @validate_types(output=dict)
    def serialize(self)->dict:
        r"""
        It provides the values of attributes defined with PyAutomation Models

        # Returns

        - dict: Serialized state machine
        """
        result = {
            "state": self.current_state.value
        }
        result.update(self.get_serialized_models())
        
        return result
    
    # TRANSITIONS
    def on_start_to_wait(self):
        r"""
        It's executed one time before enter to Wait state from Sleep state 
        """
        self.last_state = "start"
        self.criticity.value = 1

    def on_wait_to_run(self):
        r"""
        It's executed one time before enter to Run state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 1

    def on_wait_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_wait_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Wait state 
        """
        self.last_state = "wait"
        self.criticity.value = 5

    def on_run_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Run state 
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_run_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Run state 
        """
        self.last_state = "run"
        self.criticity.value = 5

    def on_reset_to_start(self):
        r"""
        It's executed one time before enter to Start state from Reset state 
        """
        self.last_state = "reset"
        self.criticity.value = 2

    def on_restart_to_wait(self):
        r"""
        It's executed one time before enter to Wait state from Restart state 
        """
        self.last_state = "restart"
        self.criticity.value = 2


class DAQ(StateMachineCore):
    r"""
    Documentation here
    """    

    def __init__(
            self,
            name:str="DAQ",
            description:str="",
            classification:str="Data Acquisition System"
        ):

        self.das = DAS()
        self.cvt = CVTEngine()

        if isinstance(name, StringType):

            name = name.value

        super(DAQ, self).__init__(
            name=name,
            description=description,
            classification=classification
            )
        
    # State Methods
    def while_waiting(self):
        r"""
        This method is executed every machine loop when it is on Wait state

        It was designed to check your buffer data in self.data, if your buffer is full, so they pass to run state
        """
        self.send('wait_to_run')

    def while_running(self):

        tags = list()

        for tag_name, tag in self.get_subscribed_tags().items():

            namespace = tag.get_node_namespace()
            opcua_address = tag.get_opcua_address()
            values = self.opcua_client_manager.get_node_value_by_opcua_address(opcua_address=opcua_address, namespace=namespace)
            if values:
                data_value = values[0][0]["DataValue"]
                value = data_value.Value.Value
                timestamp = data_value.SourceTimestamp
                tags.append({
                    "tag": tag_name,
                    "value": value,
                    "timestamp": timestamp
                })
                self.cvt.set_value(id=tag.id, value=value, timestamp=timestamp)
                self.das.buffer[tag_name]["timestamp"](timestamp)
                self.das.buffer[tag_name]["values"](self.cvt.get_value(id=tag.id))
        
        super().while_running()

    # Auxiliaries Methods
    def set_opcua_client_manager(self, manager:OPCUAClientManager):
        r"""
        Documentation here
        """
        self.opcua_client_manager = manager
    

class AutomationStateMachine(StateMachineCore):
    r"""
    Documentation here
    """
    # States
    testing = State('test')
    sleeping = State('sleep')

    # Transitions
    test_to_restart = testing.to(StateMachineCore.restarting)
    sleep_to_restart = sleeping.to(StateMachineCore.restarting)
    test_to_reset = testing.to(StateMachineCore.resetting)
    sleep_to_reset = sleeping.to(StateMachineCore.resetting)
    run_to_test = StateMachineCore.running.to(testing)
    wait_to_test = StateMachineCore.waiting.to(testing)
    run_to_sleep = StateMachineCore.running.to(sleeping)
    wait_to_sleep = StateMachineCore.waiting.to(sleeping)
    

    def while_testing(self):
        r"""
        This method is executed every machine loop when it is on Test state
        """
        self.criticity.value = 3

    def while_sleeping(self):
        r"""
        This method is executed every machine loop when it is on Sleep state
        """
        self.criticity.value = 5

    # Transitions
    def on_test_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4

    def on_test_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Test state 
        """
        self.last_state = "test"
        self.criticity.value = 4

    def on_sleep_to_restart(self):
        r"""
        It's executed one time before enter to Restart state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4

    def on_sleep_to_reset(self):
        r"""
        It's executed one time before enter to Reset state from Sleep state 
        """
        self.last_state = "sleep"
        self.criticity.value = 4


