try:
    from .temperatur import TemperaturMessung
except ImportError:
    pass  # nidaqmx nicht installiert – TemperaturMessung nicht verfügbar

from .druck import DruckMessung
