from pathlib import Path
SQL = Path("supabase/migrations/20260914113000_p0_p3_improvements.sql").read_text()

def test_every_new_public_table_enables_rls():
    for table in ("aifa_catalog","terapie","caregiver_access","audit_events"):
        assert f"alter table public.{table} enable row level security" in SQL

def test_access_contract():
    assert "caregiver_read_medicines" in SQL
    assert "shares_owner_delete" in SQL

def test_security_definer_functions_are_locked_down():
    for signature in ("invite_caregiver(text,text)","replace_aifa_catalog(jsonb)","delete_own_account()","handle_new_user()"):
        assert f"revoke all on function public.{signature} from public" in SQL
