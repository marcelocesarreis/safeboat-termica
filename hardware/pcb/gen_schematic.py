# -*- coding: utf-8 -*-
"""
SAFEBOAT TERMICA v1 — gerador do esquemático (.kicad_sch, KiCad 10).
Mesma netlist pino a pino do make_board.py, com símbolos oficiais das bibliotecas do KiCad,
o símbolo Espressif do ESP32-C3-MINI-1 (lib/) e símbolos próprios (lib SAFEBOAT) p/ AP63203,
MLX90640 e pads de fio. Cada pino recebe um toco de fio + label de rede ("netlist legível");
conferido por ERC e por comparação de netlist com a placa (compare_netlist.py).

  python gen_schematic.py            # grava kicad/safeboat-termica-v1.kicad_sch
"""
import os, re, uuid, math, json

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
KSYM = os.path.expandvars(r"%LOCALAPPDATA%\Programs\KiCad\10.0\share\kicad\symbols")
LSYM = os.path.join(OUT_DIR, "lib")
PROJECT = "safeboat-termica-v1"
SCH_PATH = os.path.join(OUT_DIR, "kicad", PROJECT + ".kicad_sch")
ROOT_UUID = "7e2c4b10-5a1e-4c1e-9c1d-0000000000a1"


def U():
    return str(uuid.uuid4())


def sym_block(txt, name):
    m = re.search(r'\(symbol "%s"' % re.escape(name), txt)
    if not m:
        raise RuntimeError("simbolo %s nao achado" % name)
    i, d = m.start(), 0
    while True:
        c = txt[i]
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d == 0:
                return txt[m.start():i + 1]
        i += 1


def sym_pins(block):
    out = []
    for pm in re.finditer(r'\(pin\s+(\w+)\s+\w+\s*\(at\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\)\s*\(length\s+([-\d.]+)\)[\s\S]*?\(name\s+"([^"]*)"[\s\S]*?\(number\s+"([^"]*)"', block):
        out.append(dict(num=pm.group(7), name=pm.group(6), etype=pm.group(1),
                        x=float(pm.group(2)), y=float(pm.group(3)), ang=float(pm.group(4)), length=float(pm.group(5))))
    return out


LIBS = {}


def load_symbol(lib, name):
    key = lib + ":" + name
    if key in LIBS:
        return LIBS[key]
    path = os.path.join(KSYM, lib + ".kicad_sym")
    if not os.path.exists(path):
        path = os.path.join(LSYM, lib + ".kicad_sym")
    txt = open(path, encoding="utf-8").read()
    b = sym_block(txt, name)
    b = b.replace('(symbol "%s"' % name, '(symbol "%s"' % key, 1)
    LIBS[key] = dict(block=b, pins=sym_pins(b))
    return LIBS[key]


PIN_TMPL = '''			(pin %(etype)s line
				(at %(x)s %(y)s %(ang)s)
				(length 2.54)
				(name "%(name)s"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
				(number "%(num)s"
					(effects
						(font
							(size 1.27 1.27)
						)
					)
				)
			)
'''


def prop(name, val, x, y, hide=False, rot=0, justify=None):
    return '''		(property "%s" "%s"
			(at %s %s %s)
			(show_name no)
			(do_not_autoplace no)
%s			(effects
				(font
					(size 1.27 1.27)
				)
%s			)
		)
''' % (name, val, x, y, rot, "\t\t\t(hide yes)\n" if hide else "",
       ("\t\t\t\t(justify %s)\n" % justify) if justify else "")


def make_custom(name, pins, desc, value, w=10.16, h=12.7):
    """símbolo próprio (lib SAFEBOAT): pins = [(num, nome, etype, x, y, ang)]"""
    body = "".join(PIN_TMPL % dict(etype=e, x=x, y=y, ang=a, name=n, num=num) for num, n, e, x, y, a in pins)
    b = '''(symbol "SAFEBOAT:%s"
		(pin_names
			(offset 1.016)
		)
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
''' % name + prop("Reference", "U", 0, h + 5.08) + prop("Value", value, 0, -h - 5.08) + prop("Footprint", "", 0, 0, True) + prop("Datasheet", "", 0, 0, True) + prop("Description", desc, 0, 0, True) + '''		(symbol "%s_0_1"
			(rectangle
				(start %s %s)
				(end %s %s)
				(stroke
					(width 0.254)
					(type default)
				)
				(fill
					(type background)
				)
			)
		)
		(symbol "%s_1_1"
''' % (name, -w, h, w, -h, name) + body + '''		)
		(embedded_fonts no)
	)'''
    LIBS["SAFEBOAT:" + name] = dict(block=b, pins=[dict(num=num, name=n, etype=e, x=x, y=y, ang=a, length=2.54) for num, n, e, x, y, a in pins])


make_custom("AP63203", [
    ("3", "VIN", "power_in", -12.7, 5.08, 0), ("2", "EN", "input", -12.7, 0, 0), ("1", "FB", "input", -12.7, -5.08, 0),
    ("6", "BST", "passive", 12.7, 5.08, 180), ("5", "SW", "power_out", 12.7, 0, 180), ("4", "GND", "power_in", 0, -12.7, 90),
], "Buck síncrono 3,8–32 V, 3,3 V fixo, 2 A, 1,1 MHz, TSOT26 (1 FB 2 EN 3 VIN 4 GND 5 SW 6 BST)", "AP63203WU-7", 7.62, 7.62)
make_custom("MLX90640", [
    ("1", "SDA", "bidirectional", -12.7, 2.54, 0), ("4", "SCL", "input", -12.7, -2.54, 0),
    ("2", "VDD", "power_in", 0, 10.16, 270), ("3", "GND", "power_in", 0, -10.16, 90),
], "Matriz IR 32x24, TO-39 4 pinos (1 SDA 2 VDD 3 GND 4 SCL), FOV 110x75", "MLX90640ESF-BAA", 7.62, 5.08)
make_custom("WirePad", [("1", "1", "passive", -7.62, 0, 0)], "Pad de fio (cabo 12 V)", "pad", 5.08, 2.54)

items = []
used_syms = {}


def r(v):
    return ("%.2f" % v).rstrip("0").rstrip(".") if abs(v - round(v)) > 1e-9 else str(int(round(v)))


def wire(x1, y1, x2, y2):
    items.append('\t(wire\n\t\t(pts\n\t\t\t(xy %s %s) (xy %s %s)\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "%s")\n\t)\n' % (r(x1), r(y1), r(x2), r(y2), U()))


def label(text, x, y, ang):
    just = {0: "left bottom", 180: "right bottom", 90: "left bottom", 270: "right bottom"}[ang]
    items.append('\t(label "%s"\n\t\t(at %s %s %s)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify %s)\n\t\t)\n\t\t(uuid "%s")\n\t)\n' % (text, r(x), r(y), ang, just, U()))


def no_connect(x, y):
    items.append('\t(no_connect\n\t\t(at %s %s)\n\t\t(uuid "%s")\n\t)\n' % (r(x), r(y), U()))


def text(t, x, y, size=2.0, bold=False):
    items.append('\t(text "%s"\n\t\t(exclude_from_sim no)\n\t\t(at %s %s 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size %s %s)\n%s\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "%s")\n\t)\n' % (t, r(x), r(y), size, size, "\t\t\t\t(bold yes)\n" if bold else "", U()))


NETS = {}   # ref -> {pin: net}


def place(ref, lib, name, X, Y, value, footprint, nets, desc="", stub=2.54, dnp=False):
    X = round(X / 1.27) * 1.27; Y = round(Y / 1.27) * 1.27
    s = load_symbol(lib, name) if lib != "SAFEBOAT" else LIBS["SAFEBOAT:" + name]
    key = lib + ":" + name
    used_syms[key] = s["block"]
    NETS[ref] = {k: v for k, v in nets.items() if k != "__nc__" and v != "NC"}
    maxy = max([abs(p["y"]) for p in s["pins"]] + [2.54])
    if s["pins"] and all(abs(p["x"]) < 1e-6 for p in s["pins"]):
        rx, ry, rj = X + 2.54, Y - 1.27, "left"
        vx, vy, vj = X + 2.54, Y + 1.27, "left"
    else:
        rx, ry, rj = X - 7.62, Y - maxy - 5.08, None
        vx, vy, vj = X + 7.62, Y + maxy + 5.08, None
    pins_txt = "".join('\t\t(pin "%s"\n\t\t\t(uuid "%s")\n\t\t)\n' % (p["num"], U()) for p in s["pins"])
    hide_ref = ref.startswith("#")
    items.append('''	(symbol
		(lib_id "%s")
		(at %s %s 0)
		(unit 1)
		(exclude_from_sim no)
		(in_bom %s)
		(on_board yes)
		(dnp %s)
		(uuid "%s")
%s%s%s%s%s%s		(instances
			(project "%s"
				(path "/%s"
					(reference "%s")
					(unit 1)
				)
			)
		)
	)
''' % (key, r(X), r(Y), "no" if hide_ref else "yes", "yes" if dnp else "no", U(),
       prop("Reference", ref, r(rx), r(ry), hide_ref, 0, rj),
       prop("Value", value, r(vx), r(vy), False, 0, vj),
       prop("Footprint", footprint, r(X), r(Y), True),
       prop("Datasheet", "", r(X), r(Y), True),
       prop("Description", desc, r(X), r(Y), True),
       pins_txt, PROJECT, ROOT_UUID, ref))
    done_pts = set()
    for p in s["pins"]:
        px, py = X + p["x"], Y - p["y"]
        net = nets.get(p["num"])
        if net is None:
            if p["etype"] == "no_connect" or p["num"] in nets.get("__nc__", ()):
                if (px, py) not in done_pts:
                    no_connect(px, py); done_pts.add((px, py))
            continue
        if net == "NC":
            if (px, py) not in done_pts:
                no_connect(px, py); done_pts.add((px, py))
            continue
        if (px, py) in done_pts:
            continue
        done_pts.add((px, py))
        a = math.radians(p["ang"] + 180)
        dx, dy = round(math.cos(a)), -round(math.sin(a))
        ex, ey = px + dx * stub, py + dy * stub
        wire(px, py, ex, ey)
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        label(net, ex, ey, ang)


FP = dict(R="Resistor_SMD:R_0603_1608Metric", C="Capacitor_SMD:C_0603_1608Metric", C0805="Capacitor_SMD:C_0805_2012Metric",
          C1210="Capacitor_SMD:C_1210_3225Metric", SMA="Diode_SMD:D_SMA", SMB="Diode_SMD:D_SMB",
          SOT23="Package_TO_SOT_SMD:SOT-23", TSOT236="Package_TO_SOT_SMD:TSOT-23-6")


def R_(ref, X, Y, val, n1, n2, desc=""):
    place(ref, "Device", "R", X, Y, val, FP["R"], {"1": n1, "2": n2}, desc)


def C_(ref, X, Y, val, n1, n2, desc="", fp="C"):
    place(ref, "Device", "C", X, Y, val, FP[fp], {"1": n1, "2": n2}, desc)


# ================================================================ FOLHA
text("SAFEBOAT TERMICA v1  —  camera termica MLX90640 + ESP32-C3, 12 V do barco  ·  esquematico p/ revisao", 20, 18, 3.0, True)
text("Redes por label (mesma netlist pino a pino de make_board.py). Placa quadrada 32 x 32 mm; sensor no lado B (frente), resto no lado F (re). Montagem completa JLCPCB (2 lados).", 20, 24, 1.5)

# ---- 1 · ALIMENTACAO
text("1 · ALIMENTACAO — +12 V (borne J2) -> F1 PPTC 0,5 A -> D1 TVS SMBJ26A -> D2 SS34 (inversao) -> VIN -> U2 AP63203 (EN=VIN, FB=VOUT) -> L1 4,7 uH -> 3V3  ·  USB J1 -> D3 SS14 -> VIN (bancada)  ·  R7/R8 leem VIN no ADC (GPIO0)", 20, 40, 2.0, True)
place("J2", "Connector_Generic", "Conn_01x02", 34, 62, "+12V (borne KF350)", "SAFEBOAT:KF350-3.5-2P", {"1": "VIN_RAW", "2": "GND"}, "cabo 2x0,75 mm2 pelo prensa-cabo; fusivel 1 A no cabo; 1 = +12V (quadrado) 2 = GND")
place("F1", "Device", "Polyfuse", 56, 60, "PPTC 0.5A 60V", "Fuse:Fuse_1812_4532Metric", {"1": "VIN_RAW", "2": "VIN_F"}, "SMD1812P050TF/60 — 2a barreira")
place("D1", "Device", "D_TVS", 76, 60, "SMAJ26A", FP["SMA"], {"1": "VIN_F", "2": "GND"}, "TVS 26 V standoff, 400 W (alternador / cargas indutivas)")
place("D2", "Device", "D_Schottky", 96, 60, "SS34", FP["SMA"], {"2": "VIN_F", "1": "VIN"}, "serie: inversao de polaridade")
C_("C5", 116, 60, "10u/50V", "VIN", "GND", "entrada do buck", "C1210")
place("U2", "SAFEBOAT", "AP63203", 150, 62, "AP63203WU-7", FP["TSOT236"], {"3": "VIN", "2": "VIN", "1": "3V3", "6": "BST", "5": "SW", "4": "GND"},
      "buck 3,3 V fixo; EN ligado a VIN (datasheet: 'attach to VIN'); FB direto no VOUT")
C_("C8", 176, 60, "100n", "SW", "BST", "bootstrap")
place("L1", "Device", "L", 196, 60, "4.7u SWPA4020S", "Inductor_SMD:L_Sunlord_SWPA4020S", {"1": "SW", "2": "3V3"}, "4x4x2 mm, 1,34 A")
C_("C6", 214, 60, "22u", "3V3", "GND", "saida", "C0805")
C_("C7", 228, 60, "22u", "3V3", "GND", "saida", "C0805")
R_("R7", 248, 60, "200k", "VIN", "VSENSE", "leitura da tensao do barco: VIN/11")
R_("R8", 262, 60, "20k", "VSENSE", "GND", "divisor")
C_("C4", 276, 60, "100n", "VSENSE", "GND", "filtro do ADC")
place("J1", "Connector_Generic", "Conn_01x04", 34, 96, "USB (JST-PH 4)", "Connector_JST:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical",
      {"1": "VBUS", "2": "USB_DM", "3": "USB_DP", "4": "GND"}, "rabicho p/ USB-C femea: 1 5V · 2 D- · 3 D+ · 4 GND")
place("D3", "Device", "D_Schottky", 62, 96, "SS14", FP["SMA"], {"2": "VBUS", "1": "VIN"}, "USB alimenta a placa na bancada (sem 12 V)")

# ---- 2 · MCU
text("2 · MCU — ESP32-C3-MINI-1: GPIO8 SDA · GPIO9 SCL (+BOOT) · GPIO10 LED · GPIO4 SENS_OFF · GPIO0 VSENSE · GPIO18/19 USB · EN com R1/C1 + RST", 20, 122, 2.0, True)
esp = load_symbol("Espressif", "ESP32-C3-MINI-1")
BY_NAME = {"GND": "GND", "3V3": "3V3", "EN": "EN", "GPIO8": "SDA", "GPIO9": "SCL", "GPIO10": "LED_IO", "GPIO4": "SENS_OFF",
           "GPIO0": "VSENSE", "GPIO18": "USB_DM", "GPIO19": "USB_DP"}
esp_nets = {}
nc = []
for p in esp["pins"]:
    key = p["name"].upper().split("/")[0]
    if p["name"].upper() in BY_NAME:
        esp_nets[p["num"]] = BY_NAME[p["name"].upper()]
    elif key in BY_NAME:
        esp_nets[p["num"]] = BY_NAME[key]
    else:
        nc.append(p["num"])
esp_nets["__nc__"] = tuple(nc)
place("U1", "Espressif", "ESP32-C3-MINI-1", 72, 190, "ESP32-C3-MINI-1-N4", "Espressif:ESP32-C3-MINI-1", esp_nets, "modulo Wi-Fi 4 / BLE 5, USB-serial nativo")
C_("C9", 130, 150, "10u", "3V3", "GND", "desacoplo", "C0805")
C_("C10", 144, 150, "100n", "3V3", "GND", "desacoplo")
R_("R1", 158, 150, "10k", "3V3", "EN", "pull-up EN")
C_("C1", 172, 150, "1u", "EN", "GND", "RC do EN")
place("SW2", "Switch", "SW_Push", 200, 150, "RST", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", {"1": "EN", "2": "GND"}, "KMR221GLFS")
place("SW1", "Switch", "SW_Push", 232, 150, "BOOT", "Button_Switch_SMD:SW_Push_1P1T_NO_CK_KMR2", {"1": "SCL", "2": "GND"}, "KMR221GLFS — BOOT = GPIO9 (= SCL; pull-up R3)")
R_("R4", 130, 186, "1k", "LED_IO", "LED_A", "LED de estado (GPIO10)")
place("LED1", "Device", "LED", 150, 186, "LED ambar", "LED_SMD:LED_0603_1608Metric", {"2": "LED_A", "1": "GND"}, "LTST-C190KFKT")

# ---- 3 · SENSOR
text("3 · SENSOR — MLX90640 110 graus no lado B (frente, janela de germanio). VDD_MLX = 3V3 via Q1 (PMOS ligado por padrao); GPIO4 alto = sensor desligado. Pull-ups I2C p/ VDD_MLX.", 20, 222, 2.0, True)
place("U3", "SAFEBOAT", "MLX90640", 50, 250, "MLX90640ESF-BAA", "SAFEBOAT:MLX90640_TO-39", {"1": "SDA", "4": "SCL", "2": "VDD_MLX", "3": "GND"},
      "TO-39 110x75 graus: 1 SDA 2 VDD 3 GND 4 SCL — THT no lado da frente (C17380659)")
C_("C2", 84, 246, "100n", "VDD_MLX", "GND", "desacoplo junto ao VDD (datasheet)")
C_("C3", 98, 246, "10u", "VDD_MLX", "GND", "reserva p/ rajadas de I2C/conversao")
R_("R2", 116, 246, "2k2", "VDD_MLX", "SDA", "pull-up I2C 400 kHz")
R_("R3", 130, 246, "2k2", "VDD_MLX", "SCL", "pull-up I2C (tambem BOOT do ESP)")
place("Q1", "Transistor_FET", "Q_PMOS_GSD", 160, 250, "SI2301", FP["SOT23"], {"1": "GATE", "2": "3V3", "3": "VDD_MLX"}, "PMOS: fonte=3V3, dreno=VDD_MLX")
R_("R5", 184, 246, "100k", "GATE", "GND", "gate a GND = sensor ligado sem firmware")
R_("R6", 198, 246, "1k", "SENS_OFF", "GATE", "GPIO4 -> gate")
for i, net in enumerate(["GND", "VIN_RAW", "VIN_F", "VIN", "VBUS", "3V3", "VDD_MLX"]):
    place("#FLG%d" % (i + 1), "power", "PWR_FLAG", 230 + 14 * i, 250, "PWR_FLAG", "", {"1": net})

sch = '''(kicad_sch
	(version 20250610)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "%s")
	(paper "A3")
	(title_block
		(title "SAFEBOAT TERMICA v1 — camera termica MLX90640 + ESP32-C3")
		(date "2026-09-22")
		(rev "v1")
		(company "SAFEBOAT Tecnologia")
		(comment 1 "Gerado por hardware/pcb/gen_schematic.py — netlist idêntica a make_board.py (PCB)")
	)
	(lib_symbols
%s	)
%s	(sheet_instances
		(path "/"
			(page "1")
		)
	)
	(embedded_fonts no)
)
''' % (ROOT_UUID, "".join("\t" + b + "\n" for b in used_syms.values()), "".join(items))
os.makedirs(os.path.dirname(SCH_PATH), exist_ok=True)
open(SCH_PATH, "w", encoding="utf-8").write(sch)
json.dump(NETS, open(os.path.join(OUT_DIR, "kicad", "sch_nets.json"), "w"), indent=1)
print("esquematico gravado:", SCH_PATH, "| simbolos:", len(used_syms), "| itens:", len(items))
