import time
from hardware.geraete import get_xsp01r

x = get_xsp01r()

def show(label):
    st = x.status()
    print(f"{label}: bits={st['bits_roh']}")

print("=== TEST KRYO 1 ===")

# alles aus
x._ausgaenge_setzen(0)
time.sleep(1)
show("Start")

# EIN: erst System, dann Remote
print("\nKryo 1 EIN")
x.kryo1_system_ein()
time.sleep(1)
x.kryo1_remote_ein()
time.sleep(2)
show("Nach EIN")

# AUS: erst System aus, dann Remote aus
print("\nKryo 1 AUS")
x.kryo1_system_aus()
time.sleep(1)
x.kryo1_remote_aus()
time.sleep(2)
show("Nach AUS")


print("\n=== TEST KRYO 2 ===")

# alles aus
x._ausgaenge_setzen(0)
time.sleep(1)
show("Start")

# EIN: erst System, dann Remote
print("\nKryo 2 EIN")
x.kryo2_system_ein()
time.sleep(1)
x.kryo2_remote_ein()
time.sleep(2)
show("Nach EIN")

# AUS: erst System aus, dann Remote aus
print("\nKryo 2 AUS")
x.kryo2_system_aus()
time.sleep(1)
x.kryo2_remote_aus()
time.sleep(2)
show("Nach AUS")

print("\n=== FERTIG ===")