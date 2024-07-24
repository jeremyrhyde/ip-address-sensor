# Standard library
import subprocess
from typing import Any, Dict, Mapping, Optional
from typing_extensions import Self

# Viam module
from viam.components.sensor import Sensor
from viam.logging import getLogger
from viam.module.types import Reconfigurable, Stoppable
from viam.proto.app.robot import ComponentConfig
from viam.proto.common import  ResourceName
from viam.resource.base import ResourceBase
from viam.resource.types import Model, ModelFamily

LOGGER = getLogger(__name__)

class IPSensor(Sensor, Reconfigurable, Stoppable):
    family = ModelFamily("viam", "sensor")
    MODEL = Model(family, "ip-address")

    cmd: str
    
    @classmethod
    def new(cls, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]) -> Self:
        service = cls(config.name)
        service.validate(config)
        service.reconfigure(config, dependencies)
        return service

    @classmethod
    def validate(cls, config: ComponentConfig) -> None:
        return None

    def reconfigure(self, config: ComponentConfig, dependencies: Mapping[ResourceName, ResourceBase]) -> None:

        def get_attribute_from_config(attribute_name: str, default, of_type=None):
            if attribute_name not in config.attributes.fields:
                return default

            if default is None:
                if of_type is None:
                    raise Exception(
                        "If default value is None, of_type argument can't be empty"
                    )
                type_default = of_type
            else:
                type_default = type(default)

            if type_default == bool:
                return config.attributes.fields[attribute_name].bool_value
            elif type_default == int:
                return int(config.attributes.fields[attribute_name].number_value)
            elif type_default == float:
                return config.attributes.fields[attribute_name].number_value
            elif type_default == str:
                return config.attributes.fields[attribute_name].string_value
            elif type_default == list:
                return list(config.attributes.fields[attribute_name].list_value)
            elif type_default == dict:
                return dict(config.attributes.fields[attribute_name].struct_value)
    
        # Extract dial_info
        self.cmd = get_attribute_from_config("cmd", None, str)

        return None

    async def get_readings(self, extra: Optional[Dict[str, Any]] = None, **kwargs) -> Mapping[str, Any]:
        p = subprocess.run(self.cmd, stdout=subprocess.PIPE, shell=True)
        output = p.stdout.decode('utf-8').strip("\n")
        return {"{}: ".format(self.cmd): output}

    async def get_geometries(self):
        raise NotImplementedError
    