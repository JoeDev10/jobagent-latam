"""
Tests de la base de datos de usuarios del SaaS (web/db.py).

Cubre el CRUD que sostiene el producto: usuarios, perfiles, settings, tokens de
reseteo de contraseña y la idempotencia de pagos (clave para no dar el upgrade
dos veces ante webhooks repetidos de Mercado Pago).

Aislamiento: como el tracker, cada test usa una DB temporal vía monkeypatch de
DB_PATH — nunca toca la DB real (data/users.db).
"""
import pytest

from web import auth


@pytest.fixture
def wdb(tmp_path, monkeypatch):
    """Módulo web.db apuntando a una DB temporal recién inicializada."""
    from web import db as db_module
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "users_test.db")
    db_module.init_db()
    return db_module


class TestUsuarios:

    def test_create_user_devuelve_id(self, wdb):
        uid = wdb.create_user("joel@example.com", "hash123", "Joel R")
        assert isinstance(uid, int) and uid > 0

    def test_create_user_crea_fila_de_settings(self, wdb):
        uid = wdb.create_user("joel@example.com", "hash123", "Joel R")
        # get_settings devuelve {} si no existe la fila → acá debe existir
        settings = wdb.get_settings(uid)
        assert settings != {}
        assert settings["preferred_portals"] == ["computrabajo"]  # default

    def test_email_duplicado_devuelve_none(self, wdb):
        wdb.create_user("dup@example.com", "h", "A")
        assert wdb.create_user("dup@example.com", "h2", "B") is None

    def test_email_se_normaliza(self, wdb):
        wdb.create_user("  Joel@Example.COM  ", "h", "Joel")
        assert wdb.get_user_by_email("joel@example.com") is not None

    def test_get_user_by_id(self, wdb):
        uid = wdb.create_user("x@example.com", "h", "X")
        u = wdb.get_user_by_id(uid)
        assert u["email"] == "x@example.com"
        assert u["full_name"] == "X"

    def test_get_user_inexistente_devuelve_none(self, wdb):
        assert wdb.get_user_by_email("nadie@example.com") is None
        assert wdb.get_user_by_id(99999) is None

    def test_plan_inicial_y_upgrade(self, wdb):
        uid = wdb.create_user("p@example.com", "h", "P")
        assert wdb.get_user_by_id(uid)["plan"] == "free"
        wdb.set_user_plan(uid, "pro")
        u = wdb.get_user_by_id(uid)
        assert u["plan"] == "pro"
        assert u["upgraded_at"]

    def test_increment_run_count(self, wdb):
        uid = wdb.create_user("r@example.com", "h", "R")
        wdb.increment_run_count(uid)
        wdb.increment_run_count(uid)
        assert wdb.get_user_by_id(uid)["runs_used"] == 2

    def test_update_password_funciona_con_verify(self, wdb):
        uid = wdb.create_user("c@example.com", auth.hash_password("vieja"), "C")
        wdb.update_password(uid, auth.hash_password("nueva"))
        u = wdb.get_user_by_id(uid)
        assert auth.verify_password("nueva", u["password"]) is True
        assert auth.verify_password("vieja", u["password"]) is False

    def test_get_user_count_y_all_users(self, wdb):
        assert wdb.get_user_count() == 0
        wdb.create_user("a@example.com", "h", "A")
        wdb.create_user("b@example.com", "h", "B")
        assert wdb.get_user_count() == 2
        assert len(wdb.get_all_users()) == 2


class TestPerfilYSettings:

    def test_save_y_get_profile_round_trip(self, wdb):
        uid = wdb.create_user("perf@example.com", "h", "Perf")
        perfil = {"full_name": "Joel", "skills": ["python", "qa"], "exp": 2}
        wdb.save_profile(uid, perfil)
        assert wdb.get_profile(uid) == perfil

    def test_save_profile_es_upsert(self, wdb):
        uid = wdb.create_user("perf@example.com", "h", "Perf")
        wdb.save_profile(uid, {"v": 1})
        wdb.save_profile(uid, {"v": 2})
        assert wdb.get_profile(uid) == {"v": 2}

    def test_get_profile_inexistente_devuelve_none(self, wdb):
        uid = wdb.create_user("perf@example.com", "h", "Perf")
        assert wdb.get_profile(uid) is None

    def test_update_settings(self, wdb):
        uid = wdb.create_user("s@example.com", "h", "S")
        wdb.update_settings(uid, computrabajo_email="cv@x.com")
        assert wdb.get_settings(uid)["computrabajo_email"] == "cv@x.com"

    def test_update_settings_portales_lista_se_serializa(self, wdb):
        uid = wdb.create_user("s@example.com", "h", "S")
        wdb.update_settings(uid, preferred_portals=["computrabajo", "bumeran"])
        assert wdb.get_settings(uid)["preferred_portals"] == ["computrabajo", "bumeran"]


class TestResetTokens:

    def test_crear_y_recuperar_token(self, wdb):
        uid = wdb.create_user("t@example.com", "h", "T")
        wdb.create_reset_token(uid, "tok-abc", "2099-01-01T00:00:00")
        row = wdb.get_reset_token("tok-abc")
        assert row is not None
        assert row["user_id"] == uid

    def test_token_usado_no_se_recupera(self, wdb):
        uid = wdb.create_user("t@example.com", "h", "T")
        wdb.create_reset_token(uid, "tok-abc", "2099-01-01T00:00:00")
        wdb.mark_token_used("tok-abc")
        assert wdb.get_reset_token("tok-abc") is None

    def test_token_inexistente_devuelve_none(self, wdb):
        assert wdb.get_reset_token("no-existe") is None


class TestPagosIdempotencia:
    """upsert_payment devuelve (created, already_approved): la red de seguridad
    para no dar el upgrade dos veces ante webhooks repetidos."""

    def test_primer_pago_es_created(self, wdb):
        uid = wdb.create_user("pay@example.com", "h", "Pay")
        created, already = wdb.upsert_payment("mp-1", uid, {"status": "approved"})
        assert created is True
        assert already is False

    def test_mismo_pago_aprobado_repetido_marca_already_approved(self, wdb):
        uid = wdb.create_user("pay@example.com", "h", "Pay")
        wdb.upsert_payment("mp-1", uid, {"status": "approved"})
        created, already = wdb.upsert_payment("mp-1", uid, {"status": "approved"})
        assert created is False
        assert already is True   # → el handler NO debe volver a upgradear

    def test_transicion_pending_a_approved(self, wdb):
        uid = wdb.create_user("pay@example.com", "h", "Pay")
        c1, a1 = wdb.upsert_payment("mp-2", uid, {"status": "pending"})
        assert (c1, a1) == (True, False)
        # pasa a approved: como el estado previo era pending, NO estaba approved aún
        c2, a2 = wdb.upsert_payment("mp-2", uid, {"status": "approved"})
        assert c2 is False
        assert a2 is False   # → el handler SÍ debe upgradear en esta transición

    def test_get_user_payments(self, wdb):
        uid = wdb.create_user("pay@example.com", "h", "Pay")
        wdb.upsert_payment("mp-1", uid, {"status": "approved"})
        pagos = wdb.get_user_payments(uid)
        assert len(pagos) == 1
        assert pagos[0]["mp_payment_id"] == "mp-1"
