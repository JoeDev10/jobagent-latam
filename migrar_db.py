"""
Migracion de base de datos: agrega columnas faltantes a la tabla applications.
Ejecutar UNA SOLA VEZ desde el directorio del proyecto:
    python migrar_db.py
"""
import sqlite3
from pathlib import Path
import shutil
from datetime import datetime

DB_PATH = Path("data/jobagent.db")
BACKUP_PATH = Path(f"data/jobagent_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")

def main():
    if not DB_PATH.exists():
        print(f"ERROR: No se encontro la base de datos en {DB_PATH}")
        return

    # Hacer backup antes de migrar
    shutil.copy2(DB_PATH, BACKUP_PATH)
    print(f"Backup creado: {BACKUP_PATH}")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Columnas a agregar en applications
    columnas_nuevas = [
        ("title",           "TEXT"),
        ("company",         "TEXT"),
        ("portal",          "TEXT"),
        ("url",             "TEXT"),
        ("location",        "TEXT"),
        ("salary_range",    "TEXT"),
        ("relevance_score", "REAL"),
        ("adapted_cv_path", "TEXT"),
    ]

    print("\nAgregando columnas faltantes...")
    for col_name, col_type in columnas_nuevas:
        try:
            conn.execute(f"ALTER TABLE applications ADD COLUMN {col_name} {col_type}")
            print(f"  + {col_name} ({col_type})")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"  = {col_name} (ya existe, skip)")
            else:
                print(f"  ! {col_name}: {e}")

    conn.commit()

    # Backfill: completar datos desde la tabla jobs
    print("\nCompletando datos desde jobs...")
    updated = conn.execute("""
        UPDATE applications
        SET
            title           = (SELECT title FROM jobs WHERE jobs.id = applications.job_id),
            company         = (SELECT company FROM jobs WHERE jobs.id = applications.job_id),
            portal          = (SELECT portal FROM jobs WHERE jobs.id = applications.job_id),
            url             = (SELECT url FROM jobs WHERE jobs.id = applications.job_id),
            location        = (SELECT location FROM jobs WHERE jobs.id = applications.job_id),
            salary_range    = (SELECT salary_range FROM jobs WHERE jobs.id = applications.job_id),
            relevance_score = (SELECT relevance_score FROM jobs WHERE jobs.id = applications.job_id)
        WHERE title IS NULL
    """).rowcount
    conn.commit()
    print(f"  {updated} aplicaciones actualizadas")

    # Verificar
    print("\nAplicaciones en la base de datos:")
    rows = conn.execute(
        "SELECT title, company, portal, status, relevance_score FROM applications ORDER BY relevance_score DESC"
    ).fetchall()
    for r in rows:
        score = r['relevance_score'] or 0
        print(f"  [{r['portal']}] {r['title']} @ {r['company']} | score: {score:.0%} | {r['status']}")

    conn.close()
    print(f"\nMigracion completada! Total: {len(rows)} aplicaciones.")
    print("\nAhora podes abrir el dashboard con: python main.py dashboard")
    input("\nPresiona Enter para cerrar...")


if __name__ == "__main__":
    import os
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    main()
