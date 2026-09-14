from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


MEDICINE_FIELDS = (
    "id,user_id,nome,descrizione,principio_attivo,quantita,tipo,scadenza,aic,barcode,"
    "soglia_scorta,reminder_days,dosaggio,orari,note_mediche,photo_path,created_at,updated_at,deleted_at"
)


class MedicineRepository:
    def __init__(self, supabase, user_id: str):
        self.sb = supabase
        self.user_id = user_id

    def medicines(self, include_deleted=False):
        query = self.sb.table("farmaci").select(MEDICINE_FIELDS).order("nome")
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        return query.execute().data or []

    def owned_medicines(self, include_deleted=False):
        return [row for row in self.medicines(include_deleted) if row.get("user_id") == self.user_id]

    def create_medicine(self, payload: dict):
        payload = {**payload, "user_id": self.user_id}
        return self.sb.table("farmaci").insert(payload).execute().data

    def update_medicine(self, medicine_id: int, payload: dict):
        payload = {**payload, "updated_at": datetime.now(timezone.utc).isoformat()}
        return self.sb.table("farmaci").update(payload).eq("id", medicine_id).execute().data

    def trash(self, medicine_id: int):
        return self.update_medicine(medicine_id, {"deleted_at": datetime.now(timezone.utc).isoformat()})

    def restore(self, medicine_id: int):
        return self.update_medicine(medicine_id, {"deleted_at": None})

    def permanently_delete(self, medicine_id: int):
        return self.sb.table("farmaci").delete().eq("id", medicine_id).execute().data

    def catalog_lookup(self, value: str):
        from barcode_scanner import medicine_lookup_candidates
        from medicine_core import normalize_aic

        fields = "aic,descrizione,principio_attivo,ditta,barcode"
        for candidate in medicine_lookup_candidates(value):
            by_barcode = self.sb.table("aifa_catalog").select(fields).eq("barcode", candidate).maybe_single().execute()
            if by_barcode.data:
                return by_barcode.data
            normalized = normalize_aic(candidate)
            if normalized:
                by_aic = self.sb.table("aifa_catalog").select(fields).eq("aic", normalized).maybe_single().execute()
                if by_aic.data:
                    return by_aic.data
        return None

    def catalog_count(self):
        result = self.sb.table("aifa_catalog").select("aic", count="exact").limit(1).execute()
        return result.count or 0

    def import_catalog(self, rows: list[dict]):
        # Server-side RPC performs replacement in one transaction.
        return self.sb.rpc("replace_aifa_catalog", {"rows": rows}).execute().data

    def treatments(self):
        return self.sb.table("terapie").select("*").order("created_at", desc=True).execute().data or []

    def add_treatment(self, payload: dict):
        return self.sb.table("terapie").insert({**payload, "user_id": self.user_id}).execute().data

    def delete_treatment(self, treatment_id: int):
        return self.sb.table("terapie").delete().eq("id", treatment_id).execute().data

    def shares(self):
        return self.sb.table("caregiver_access").select("id,owner_id,caregiver_id,label,created_at").execute().data or []

    def invite_caregiver(self, email: str, label: str):
        return self.sb.rpc("invite_caregiver", {"caregiver_email": email.strip().lower(), "share_label": label.strip() or None}).execute().data

    def remove_share(self, share_id: int):
        return self.sb.table("caregiver_access").delete().eq("id", share_id).execute().data

    def audit_events(self, limit=100):
        return self.sb.table("audit_events").select("id,action,table_name,row_id,created_at").order("created_at", desc=True).limit(limit).execute().data or []

    def upload_photo(self, uploaded_file):
        ext = (uploaded_file.name.rsplit(".", 1)[-1] if "." in uploaded_file.name else "jpg").lower()
        if ext not in {"jpg", "jpeg", "png", "webp"}:
            raise ValueError("Formato immagine non supportato.")
        raw = uploaded_file.getvalue()
        if len(raw) > 5_000_000:
            raise ValueError("L'immagine supera il limite di 5 MB.")
        path = f"{self.user_id}/{uuid4().hex}.{ext}"
        self.sb.storage.from_("medicine-photos").upload(path, raw, {"content-type": uploaded_file.type, "upsert": "false"})
        return path

    def signed_photo_url(self, path: str):
        result = self.sb.storage.from_("medicine-photos").create_signed_url(path, 300)
        return result.get("signedURL") or result.get("signedUrl")
