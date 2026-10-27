import ast
import json
from datetime import datetime
from .models import Roast, RoastEvent, BeanInfo


def _load_payload(file_obj):
    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        obj = ast.literal_eval(raw)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Invalid .alog format: {e}")
    if not isinstance(obj, dict):
        raise ValueError("Parsed content is not a dict")
    return obj


def _to_grams(weight_field):
    if not weight_field or len(weight_field) < 3:
        return None
    val = weight_field[0]
    unit = weight_field[2]
    if not val or val <= 0:
        return None
    factor = {"g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}.get(unit, 1.0)
    return float(val) * factor


def _to_celsius(temp_array, mode):
    """Convert temperatures to Celsius based on Artisan's mode flag."""
    if not temp_array or mode != "F":
        return temp_array
    # Convert Fahrenheit to Celsius
    return [((t - 32) * 5.0 / 9.0) if t is not None else None for t in temp_array]


def _events_from_data(data, mode):
    out = []
    computed = data.get("computed", {}) or {}
    type_map = {-1: "TP", 0: "CHARGE", 1: "DRY", 2: "FCs", 6: "DROP"}
    
    computed_bt_keys = {
        "CHARGE": "CHARGE_BT",
        "TP": "TP_BT",
        "DRY": "DRY_BT",
        "FCs": "FCs_BT",
        "DROP": "DROP_BT"
    }

    def convert_temp(t):
        return _to_celsius([t], mode)[0] if t is not None else None

    if "anno_positions" in data and data["anno_positions"]:
        for anno in data["anno_positions"]:
            if not anno or len(anno) < 2:
                continue
            code = anno[0]
            if code in type_map:
                evt_type = type_map[code]
                # Grab the exact computed BT value
                bt_val = computed.get(computed_bt_keys.get(evt_type))
                out.append({
                    "type": evt_type,
                    "time": float(anno[1]),
                    "bt": convert_temp(bt_val), # <--- Applies the Celsius conversion properly
                })
    return out # <--- Moved to the bottom


def parse_alog(file_obj, user=None) -> Roast:
    data = _load_payload(file_obj)
    mode = data.get("mode", "C")

    timex = data.get("timex") or []
    bt = data.get("temp1") or []
    et = data.get("temp2") or []
    if not timex:
        raise ValueError("Missing 'timex' array")
    if len(bt) != len(timex) or len(et) != len(timex):
        n = min(len(timex), len(bt), len(et))
        data["timex"] = timex[:n]
        data["temp1"] = bt[:n]
        data["temp2"] = et[:n]
        timex = data["timex"]
        bt = data["temp1"]
        et = data["temp2"]

    alog_uuid = data.get("roastUUID") or data.get("hash")
    if not alog_uuid:
        raise ValueError("File has no roastUUID or hash")

    existing = Roast.objects.filter(alog_uuid=alog_uuid).first()
    if existing:
        return existing

    roast_date = None
    if data.get("roastisodate"):
        try:
            roast_date = datetime.strptime(data["roastisodate"], "%Y-%m-%d").date()
        except ValueError:
            pass

    roast_time = None
    if data.get("roasttime"):
        try:
            roast_time = datetime.strptime(data["roasttime"], "%H:%M:%S").time()
        except ValueError:
            pass

    extra = {}
    names = data.get("extraname1") or []
    times = data.get("extratimex") or []
    temps1 = data.get("extratemp1") or []
    for i, name in enumerate(names):
        if i < len(times) and i < len(temps1):
            extra[name] = {
                "time": times[i],
                "temp": _to_celsius(temps1[i], mode),
            }

    computed = data.get("computed", {}) or {}
    weight_in = _to_grams(data.get("weight"))
    weight_loss_pct = computed.get("weight_loss")
    weight_out = None
    if weight_loss_pct is not None and weight_loss_pct >= 100.0:
        weight_loss_pct = None
    elif weight_in and weight_loss_pct is not None:
        weight_out = weight_in * (1 - weight_loss_pct / 100.0)

    title_str = data.get("title", "").strip()
    beans_str = data.get("beans", "").strip()
    generic_titles = ["Roaster Scope", "Untitled", ""]
    if title_str and title_str not in generic_titles:
        display_name = title_str
    else:
        display_name = beans_str

    roaster_type = data.get("roastertype") or data.get("machinesetup") or ""
    roaster_org = data.get("organization") or ""
    operator = data.get("operator") or ""
    
    batch_nr = data.get("roastbatchnr")
    if batch_nr is not None:
        try:
            batch_nr = int(batch_nr)
        except (ValueError, TypeError):
            batch_nr = None

    bean_info = None
    if display_name:
        bean_info = BeanInfo.objects.filter(name__iexact=display_name).first()
        if not bean_info:
            bean_info = BeanInfo.objects.filter(name__icontains=display_name).first()

    origin = ""
    if bean_info and bean_info.origin:
        origin = bean_info.origin
    else:
        origins = ["Kenya", "Guatemala", "Ethiopia", "Colombia", "Brazil", "Sumatra", "Costa Rica", "Panama", "Honduras", "Mexico", "Peru", "Rwanda", "Burundi", "Yemen", "Indonesia", "Vietnam", "India"]
        for o in origins:
            if o.lower() in display_name.lower():
                origin = o
                break

    # Convert main curves to Celsius
    temp_et_c = _to_celsius(data.get("temp1", []), mode)
    temp_bt_c = _to_celsius(data.get("temp2", []), mode)

    roast = Roast.objects.create(
        alog_uuid=alog_uuid,
        uploaded_by=user,
        owner=None,
        bean_info=bean_info,
        title=title_str,
        beans=display_name,
        origin=origin,
        roast_date=roast_date,
        roast_time=roast_time,
        batch_nr=batch_nr,
        operator=operator,
        organization=roaster_org,
        roaster_type=roaster_type,
        ambient_temp=_to_celsius([data.get("ambientTemp")], mode)[0] if data.get("ambientTemp") else None,
        weight_in_g=weight_in,
        weight_out_g=weight_out,
        weight_loss_pct=weight_loss_pct,
        timex=data.get("timex", []),
        temp_bt=temp_bt_c,
        temp_et=temp_et_c,
        extra_curves=extra,
        computed=computed,
        flavors=data.get("flavors", []),
        flavor_labels=data.get("flavorlabels", []),
        raw=data,
        is_public=False,
    )

    events = _events_from_data(data, mode)
    for e in events:
        RoastEvent.objects.create(
            roast=roast,
            event_type=e["type"],
            time_s=e["time"],
            bt=e["bt"],
            et=computed.get(f"{e['type']}_ET"),
        )

    return roast