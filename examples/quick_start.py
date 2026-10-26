"""DS8034-R initial programming example."""
# Creator: Jeff Michaelis
from rigol_ds8000r import RigolDS8000R

# Use the VISA resource for YOUR oscilloscope, not the example IP address.
RESOURCE = "TCPIP0::192.168.1.50::INSTR"

with RigolDS8000R(RESOURCE, timeout=10000) as scope:
    print("Connected:", scope.idn)
    ch1 = scope.channel(1)
    # Ordinary setter/getter methods are validated at the Python layer.
    ch1.enable(True)
    ch1.coupling("DC")
    ch1.scale(0.5)
    scope.time_scale(0.001)
    scope.edge_trigger(channel=1, level=0, slope="POS")
    scope.run()
    print("Sample rate:", scope.sample_rate(), "samples/s")
    print("CH1 voltage scale:", ch1.scale(), "V/div")

    # Direct manual SCPI access covers the rest of the programming guide.
    print("Oscilloscope state:", scope.query(":TRIGger:STATus?"))
    print("Peak-to-peak:", scope.measure("VPP", 1), "V")

    # Take 1000 on-screen samples without requiring NumPy or Matplotlib.
    data = scope.waveform(channel=1, points=1000, mode="NORM")
    data.csv("channel1.csv")
    print("Saved", len(data.voltages), "samples")
