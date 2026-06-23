# -*- coding: utf-8 -*-
"""
Actualizador seguro para app_dss.py
Autor: ChatGPT para JFRodriguez

Qué corrige:
1) En la pestaña "AP semanal obs" agrega selector de semana:
   - Sábado a viernes (default)
   - Lunes a domingo
2) Recalcula resumen y detalle semanal según el modo seleccionado.
3) Corrige el error de pandas: invalid error value specified.
4) Crea respaldo antes de modificar.

Uso en Windows:
    py actualizar_app_dss_semana.py

También puede indicar el archivo:
    py actualizar_app_dss_semana.py app_dss.py
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ENCODINGS = ("utf-8-sig", "utf-8", "latin-1")

WEEK_FUNCTIONS_BLOCK = r'''
WEEK_MODE_LABELS = {
    "sat_fri": "Sábado a viernes",
    "mon_sun": "Lunes a domingo",
}


def week_mode_label(week_mode: str) -> str:
    return WEEK_MODE_LABELS.get(str(week_mode), WEEK_MODE_LABELS["sat_fri"])


WEEK_MODE_LABELS = {
    "sat_fri": "Sábado a viernes",
    "mon_sun": "Lunes a domingo",
}


def week_mode_label(week_mode: str) -> str:
    return WEEK_MODE_LABELS.get(str(week_mode), WEEK_MODE_LABELS["sat_fri"])


WEEK_MODE_LABELS = {
    "sat_fri": "Sábado a viernes",
    "mon_sun": "Lunes a domingo",
}


def week_mode_label(week_mode: str) -> str:
    return WEEK_MODE_LABELS.get(str(week_mode), WEEK_MODE_LABELS["sat_fri"])


WEEK_MODE_LABELS = {
    "sat_fri": "Sábado a viernes",
    "mon_sun": "Lunes a domingo",
}


def week_mode_label(week_mode: str) -> str:
    return WEEK_MODE_LABELS.get(str(week_mode), WEEK_MODE_LABELS["sat_fri"])


def operational_week_info(date_value, week_mode: str = "sat_fri") -> Tuple[int, pd.Timestamp, pd.Timestamp]:
    """Calcula semana según el modo seleccionado.

    sat_fri:
        Semana operativa sábado-viernes.
        Para 2026: 30-may al 05-jun = semana 23.

    mon_sun:
        Semana calendario ISO lunes-domingo.
        Para 2026: 01-jun al 07-jun = semana 23.
    """
    d = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(d):
        return 0, pd.NaT, pd.NaT

    d = d.normalize()
    week_mode = "mon_sun" if week_mode == "mon_sun" else "sat_fri"

    if week_mode == "mon_sun":
        iso = d.isocalendar()
        week = int(iso.week)
        start = d - pd.Timedelta(days=int(d.weekday()))  # lunes
        end = start + pd.Timedelta(days=6)               # domingo
        return week, start, end

    # Modo operativo original sábado-viernes
    year_start = pd.Timestamp(year=d.year, month=1, day=1)
    days_to_saturday = (5 - year_start.weekday()) % 7
    first_saturday = year_start + pd.Timedelta(days=days_to_saturday)

    if d < first_saturday:
        return 1, year_start, first_saturday - pd.Timedelta(days=1)

    week = 2 + int((d - first_saturday).days // 7)
    start = first_saturday + pd.Timedelta(days=(week - 2) * 7)
    end = start + pd.Timedelta(days=6)
    return week, start, end


def add_operational_week_columns(df: pd.DataFrame, week_mode: str = "sat_fri") -> pd.DataFrame:
    if df is None or df.empty or "Fecha_dia" not in df.columns:
        return df

    out = df.copy()
    out["Fecha_dia"] = pd.to_datetime(out["Fecha_dia"], errors="coerce").dt.normalize()
    out = out[out["Fecha_dia"].notna()].copy()

    week_mode = "mon_sun" if week_mode == "mon_sun" else "sat_fri"

    info = out["Fecha_dia"].apply(lambda x: operational_week_info(x, week_mode))
    out["Semana operativa"] = [x[0] for x in info]
    out["Inicio semana"] = [x[1] for x in info]
    out["Fin semana"] = [x[2] for x in info]
    out["Tipo semana"] = week_mode_label(week_mode)

    if week_mode == "mon_sun":
        iso = out["Fecha_dia"].dt.isocalendar()
        out["Año semana"] = iso["year"].astype(int)
    else:
        out["Año semana"] = pd.to_datetime(out["Inicio semana"], errors="coerce").dt.year.astype("Int64")

    return out

'''.lstrip()

WEEK_SELECTOR_BLOCK = r'''    week_mode = st.radio(
        "Alineación de la semana",
        options=["sat_fri", "mon_sun"],
        index=0,
        horizontal=True,
        format_func=lambda x: "Sábado a viernes" if x == "sat_fri" else "Lunes a domingo",
        key="apw_week_mode",
        help="Permite comparar el promedio semanal observado contra AP DSS usando semana operativa sábado-viernes o semana calendario lunes-domingo.",
    )

    st.caption(
        f"Promedio semanal observado alineado con la semana **{week_mode_label(week_mode)}**. "
        "Para cada semana se calcula contra todas las curvas AP DSS y se reporta el percentil más cercano "
        "por diferencia absoluta, sin importar si el DSS queda por arriba o por debajo del observado."
    )'''


def read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for enc in ENCODINGS:
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1", errors="replace"), "latin-1"


def write_text(path: Path, text: str, encoding: str) -> None:
    # Se escribe en utf-8 para mantener acentos y símbolos de unidades.
    path.write_text(text, encoding="utf-8", newline="")


def find_target_file() -> Path:
    if len(sys.argv) > 1:
        p = Path(sys.argv[1]).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"No existe el archivo indicado: {p}")
        return p

    cwd = Path.cwd()
    preferred = ["app_dss.py", "app_simulacion_dss.py"]
    for name in preferred:
        p = cwd / name
        if p.exists() and p.is_file():
            return p

    candidates = []
    for p in cwd.glob("app*.py"):
        try:
            txt, _ = read_text(p)
        except Exception:
            continue
        if "tab_aportes_obs_semanal" in txt and "_weekly_ap_obs_vs_dss_table" in txt:
            candidates.append(p)
    if candidates:
        return sorted(candidates, key=lambda x: x.stat().st_mtime, reverse=True)[0]

    raise FileNotFoundError(
        "No encontré app_dss.py ni app_simulacion_dss.py en esta carpeta. "
        "Coloque este actualizador en la misma carpeta del app o ejecútelo con: "
        "py actualizar_app_dss_semana.py nombre_del_app.py"
    )


def replace_week_functions(text: str) -> tuple[str, bool]:
    # Reemplazo principal: desde operational_week_info hasta antes de _weekly_ap_obs_vs_dss_table.
    pattern = re.compile(
        r"def\s+operational_week_info\s*\([^\)]*\)\s*->\s*Tuple\[int,\s*pd\.Timestamp,\s*pd\.Timestamp\]:.*?"
        r"def\s+add_operational_week_columns\s*\([^\)]*\)\s*->\s*pd\.DataFrame:\n.*?\n\s*return\s+out\n\n",
        re.S,
    )
    new_text, n = pattern.subn(WEEK_FUNCTIONS_BLOCK, text, count=1)
    return new_text, n > 0


def update_weekly_signature(text: str) -> tuple[str, bool]:
    pattern = re.compile(
        r"(def\s+_weekly_ap_obs_vs_dss_table\s*\(\s*\n"
        r"\s*dss_bytes:\s*bytes,\s*\n"
        r"\s*res_key:\s*str,\s*\n"
        r"\s*flow_unit:\s*str,\s*\n"
        r"\s*obs_aportes:\s*Optional\[pd\.DataFrame\],\s*\n"
        r"\s*evap_cfs:\s*float\s*=\s*0\.0,\s*\n)"
        r"(\)\s*->\s*Tuple\[pd\.DataFrame,\s*pd\.DataFrame\]:)",
        re.S,
    )
    repl = "\\1    week_mode: str = \"sat_fri\",\n\\2"
    new_text, n = pattern.subn(repl, text, count=1)
    return new_text, n > 0


def update_week_column_calls(text: str) -> tuple[str, int]:
    n_total = 0

    # base: quitar cálculo viejo de Año semana y pasar week_mode.
    pattern_base = re.compile(
        r"base\s*=\s*add_operational_week_columns\(base\)\s*\n"
        r"\s*base\[\"Año semana\"\]\s*=\s*pd\.to_datetime\(base\[\"Inicio semana\"\],\s*errors=\"coerce\"\)\.dt\.year\s*\n",
        re.S,
    )
    text, n = pattern_base.subn("base = add_operational_week_columns(base, week_mode=week_mode)\n", text, count=1)
    n_total += n

    # Respaldo si solo existe la llamada sin Año semana.
    if n == 0:
        text, n = re.subn(
            r"base\s*=\s*add_operational_week_columns\(base\)",
            "base = add_operational_week_columns(base, week_mode=week_mode)",
            text,
            count=1,
        )
        n_total += n

    pattern_obs = re.compile(
        r"obs\s*=\s*add_operational_week_columns\(obs\)\s*\n"
        r"\s*obs\[\"Año semana\"\]\s*=\s*pd\.to_datetime\(obs\[\"Inicio semana\"\],\s*errors=\"coerce\"\)\.dt\.year\s*\n",
        re.S,
    )
    text, n = pattern_obs.subn("obs = add_operational_week_columns(obs, week_mode=week_mode)\n", text, count=1)
    n_total += n

    if n == 0:
        text, n = re.subn(
            r"obs\s*=\s*add_operational_week_columns\(obs\)",
            "obs = add_operational_week_columns(obs, week_mode=week_mode)",
            text,
            count=1,
        )
        n_total += n

    return text, n_total


def update_detail_conversion(text: str) -> tuple[str, bool]:
    old = '''    if not detail.empty:
        detail = detail.sort_values(["Embalse", "Semana", "Percentil AP DSS"]).reset_index(drop=True)

        for col in detail.columns:
            if col in ("Embalse", "Percentil AP DSS"):
                continue
            if "semana" in col.lower() or "fecha" in col.lower():
                continue

            try:
                converted = pd.to_numeric(detail[col], errors="coerce")
                if converted.notna().any():
                    detail[col] = converted
            except Exception:
                pass
    return summary, detail
'''
    new = '''    if not detail.empty:
        detail = detail.sort_values(["Embalse", "Semana", "Percentil AP DSS"]).reset_index(drop=True)

        for col in detail.columns:
            if col in ("Embalse", "Percentil AP DSS"):
                continue
            if "semana" in col.lower() or "fecha" in col.lower():
                continue

            try:
                converted = pd.to_numeric(detail[col], errors="coerce")
                if converted.notna().any():
                    detail[col] = converted
            except Exception:
                pass
    return summary, detail
'''
    if old in text:
        return text.replace(old, new, 1), True

    pattern = re.compile(
        r"    if not detail\.empty:\n"
        r"        detail = detail\.sort_values\(\[\"Embalse\", \"Semana\", \"Percentil AP DSS\"\]\)\.reset_index\(drop=True\)\n"
        r"        for col in detail\.columns:\n"
        r"            if col not in \(\"Embalse\", \"Percentil AP DSS\"\):\n"
        r"                if \"semana\" not in col\.lower\(\):\n"
        r"                    detail\[col\] = pd\.to_numeric\(detail\[col\], errors=\"ignore\"\)\n"
        r"    return summary, detail\n",
        re.S,
    )
    new_text, n = pattern.subn(new, text, count=1)
    return new_text, n > 0


def add_week_selector_to_tab(text: str) -> tuple[str, bool]:
    # Reemplaza solo la primera caption inmediatamente después del subheader en tab_aportes_obs_semanal.
    pattern = re.compile(
        r"(def\s+tab_aportes_obs_semanal\s*\(.*?\)\s*->\s*None:\n"
        r"\s*\"\"\".*?\"\"\"\n"
        r"\s*st\.subheader\(\"📅 Aporte observado semanal vs AP DSS\"\)\n)"
        r"\s*st\.caption\(\n"
        r"\s*\"Promedio semanal observado alineado con la semana operativa sábado-viernes\. \"\n"
        r"\s*\"Para cada semana se calcula contra todas las curvas AP DSS y se reporta el percentil más cercano \"\n"
        r"\s*\"por diferencia absoluta, sin importar si el DSS queda por arriba o por debajo del observado\.\"\n"
        r"\s*\)\n",
        re.S,
    )
    repl = r"\1" + WEEK_SELECTOR_BLOCK + "\n"
    new_text, n = pattern.subn(repl, text, count=1)
    if n > 0:
        return new_text, True

    # Respaldo más flexible: inserta selector después del subheader si no está ya.
    if "key=\"apw_week_mode\"" in text or "key='apw_week_mode'" in text:
        return text, True
    marker = '    st.subheader("📅 Aporte observado semanal vs AP DSS")\n'
    idx = text.find(marker)
    if idx == -1:
        return text, False
    insert_at = idx + len(marker)
    new_text = text[:insert_at] + WEEK_SELECTOR_BLOCK + "\n" + text[insert_at:]
    return new_text, True


def update_weekly_call(text: str) -> tuple[str, int]:
    # Agrega week_mode a la llamada dentro de tab_aportes_obs_semanal si no existe.
    pattern = re.compile(
        r"(summary, detail = _weekly_ap_obs_vs_dss_table\(\n"
        r"\s*dss_bytes=dss_bytes,\n"
        r"\s*res_key=res_key,\n"
        r"\s*flow_unit=flow_unit,\n"
        r"\s*obs_aportes=obs_df,\n"
        r"\s*evap_cfs=evap,\n)"
        r"(\s*\))",
        re.S,
    )
    repl = r"\1                week_mode=week_mode,\n\2"
    new_text, n = pattern.subn(repl, text, count=1)
    return new_text, n


def update_download_filenames(text: str) -> tuple[str, int]:
    n_total = 0

    if "file_suffix = \"sabado_viernes\" if week_mode == \"sat_fri\" else \"lunes_domingo\"" not in text:
        marker = '    csv = show_tbl.to_csv(index=False).encode("utf-8-sig")\n'
        repl = marker + '    file_suffix = "sabado_viernes" if week_mode == "sat_fri" else "lunes_domingo"\n'
        if marker in text:
            text = text.replace(marker, repl, 1)
            n_total += 1

    old = '        f"aporte_observado_semanal_vs_dss_{file_suffix}.csv",'
    new = '        f"aporte_observado_semanal_vs_dss_{file_suffix}.csv",'
    if old in text:
        text = text.replace(old, new, 1)
        n_total += 1

    old2 = '                f"detalle_aporte_observado_semanal_todos_percentiles_{file_suffix}.csv",'
    new2 = '                f"detalle_aporte_observado_semanal_todos_percentiles_{file_suffix}.csv",'
    if old2 in text:
        text = text.replace(old2, new2, 1)
        n_total += 1

    return text, n_total


def add_type_week_to_rows(text: str) -> tuple[str, int]:
    # Añade columna de trazabilidad sin afectar filtros existentes.
    n_total = 0
    old = '            "Embalse": cfg["name"],\n            "Semana": int(r["Semana operativa"]),'
    new = '            "Embalse": cfg["name"],\n            "Tipo semana": week_mode_label(week_mode),\n            "Semana": int(r["Semana operativa"]),'
    if old in text and '"Tipo semana": week_mode_label(week_mode),' not in text:
        text = text.replace(old, new, 1)
        n_total += 1

    old_detail = '                "Embalse": cfg["name"],\n                "Semana": int(r["Semana operativa"]),'
    new_detail = '                "Embalse": cfg["name"],\n                "Tipo semana": week_mode_label(week_mode),\n                "Semana": int(r["Semana operativa"]),'
    if old_detail in text and text.count('"Tipo semana": week_mode_label(week_mode),') < 2:
        text = text.replace(old_detail, new_detail, 1)
        n_total += 1

    return text, n_total


def patch_text(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []

    text, ok = replace_week_functions(text)
    if ok:
        changes.append("Funciones de semana actualizadas")
    else:
        raise RuntimeError("No pude reemplazar operational_week_info/add_operational_week_columns. Revise que el app tenga esas funciones.")

    text, ok = update_weekly_signature(text)
    if ok:
        changes.append("Firma de _weekly_ap_obs_vs_dss_table actualizada con week_mode")
    else:
        # Si ya estaba aplicado, no fallar.
        if "week_mode: str = \"sat_fri\"" in text:
            changes.append("Firma semanal ya tenía week_mode")
        else:
            raise RuntimeError("No pude actualizar la firma de _weekly_ap_obs_vs_dss_table.")

    text, n = update_week_column_calls(text)
    if n:
        changes.append(f"Llamadas add_operational_week_columns actualizadas: {n}")
    else:
        if "add_operational_week_columns(base, week_mode=week_mode)" in text:
            changes.append("Llamadas semanales ya estaban actualizadas")
        else:
            raise RuntimeError("No pude actualizar las llamadas a add_operational_week_columns en el cálculo semanal.")

    text, ok = update_detail_conversion(text)
    if ok:
        changes.append("Corrección del error invalid error value specified aplicada")
    else:
        if 'pd.to_numeric(detail[col], errors="coerce")' in text:
            changes.append("Corrección pandas ya estaba aplicada")
        else:
            raise RuntimeError("No pude reemplazar el bloque de conversión del detalle semanal.")

    text, ok = add_week_selector_to_tab(text)
    if ok:
        changes.append("Selector sábado-viernes / lunes-domingo agregado")
    else:
        raise RuntimeError("No pude insertar el selector en tab_aportes_obs_semanal.")

    text, n = update_weekly_call(text)
    if n:
        changes.append("Llamada semanal pasa week_mode al cálculo")
    elif "week_mode=week_mode" in text:
        changes.append("Llamada semanal ya tenía week_mode")
    else:
        raise RuntimeError("No pude agregar week_mode a la llamada _weekly_ap_obs_vs_dss_table.")

    text, n = add_type_week_to_rows(text)
    if n:
        changes.append("Columna Tipo semana agregada al resumen/detalle")

    text, n = update_download_filenames(text)
    if n:
        changes.append("Nombres de descarga ajustados por tipo de semana")

    return text, changes


def main() -> int:
    target = find_target_file()
    original, enc = read_text(target)

    if "tab_aportes_obs_semanal" not in original:
        raise RuntimeError("El archivo no parece ser el app DSS esperado: no contiene tab_aportes_obs_semanal.")

    patched, changes = patch_text(original)

    if patched == original:
        print("No hubo cambios: el archivo parece estar ya actualizado.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target.with_name(f"{target.stem}_backup_antes_semana_{stamp}{target.suffix}")
    backup.write_text(original, encoding="utf-8", newline="")
    write_text(target, patched, enc)

    print("✅ App actualizado correctamente")
    print(f"Archivo modificado: {target}")
    print(f"Respaldo creado : {backup}")
    print("Cambios:")
    for c in changes:
        print(f"  - {c}")
    print("\nAhora ejecute:")
    print(f"  py -m streamlit run {target.name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"❌ Error: {exc}")
        print("\nSugerencia: copie este archivo en la misma carpeta de app_dss.py y vuelva a ejecutarlo.")
        raise SystemExit(1)
