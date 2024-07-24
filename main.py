import asyncio

from viam.components.sensor import Sensor
from viam.logging import getLogger
from viam.module.module import Module
from viam.resource.registry import Registry, ResourceCreatorRegistration
from src.ip_sensor import IPSensor

LOGGER = getLogger(__name__)

async def main():
    """This function creates and starts a new module, after adding all desired resources.
    Resources must be pre-registered. For an example, see the `__init__.py` file.
    """
    Registry.register_resource_creator(
        Sensor.SUBTYPE,
        IPSensor.MODEL,
        ResourceCreatorRegistration(IPSensor.new, IPSensor.validate),
    )

    module = Module.from_args()
    module.add_model_from_registry(Sensor.SUBTYPE, IPSensor.MODEL)
    LOGGER.debug("Starting module in main.py.")
    await module.start()


if __name__ == "__main__":
    asyncio.run(main())
