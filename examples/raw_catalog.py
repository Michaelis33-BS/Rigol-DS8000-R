"""Using the full manual SCPI command catalog."""
# Creator: Jeff Michaelis
from rigol_ds8000r import RigolDS8000R, catalog

# The catalogue is available without attaching a scope.
for row in catalog.entries(":CHANnel<n>:*"):
    print("{}  |  manual {}".format(row["syntax"], row["page"]))

with RigolDS8000R("TCPIP0::192.168.1.50::INSTR") as scope:
    # Manual-index expression: <n> is replaced by 1, bracket syntax removed.
    scale = scope.commands.get(":CHANnel<n>:SCALe", n=1)
    print("CH1 scale:", scale)
    scope.commands.set(":CHANnel<n>:SCALe", float(scale), n=1)

    # Complex query with a parameter, using exactly the manual's arguments.
    print("CH1 peak-to-peak:", scope.commands.query(":MEASure:ITEM", "VPP,CHANnel1"))

    # Fully specified direct path is always available for optional features.
    # scope.write(":BUS1:MODE SPI")
