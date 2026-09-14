create index if not exists terapie_medicine_idx on public.terapie(medicine_id);

drop policy if exists farmaci_select_own on public.farmaci;
drop policy if exists caregiver_read_medicines on public.farmaci;
create policy "farmaci_read_allowed" on public.farmaci for select to authenticated using (
  (select auth.uid()) = user_id or exists (
    select 1 from public.caregiver_access ca
    where ca.owner_id = farmaci.user_id and ca.caregiver_id = (select auth.uid())
  )
);

drop policy if exists terapie_owner_all on public.terapie;
drop policy if exists caregiver_read_treatments on public.terapie;
create policy "terapie_read_allowed" on public.terapie for select to authenticated using (
  (select auth.uid()) = user_id or exists (
    select 1 from public.caregiver_access ca
    where ca.owner_id = terapie.user_id and ca.caregiver_id = (select auth.uid())
  )
);
create policy "terapie_insert_own" on public.terapie for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "terapie_update_own" on public.terapie for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "terapie_delete_own" on public.terapie for delete to authenticated using ((select auth.uid()) = user_id);

create or replace function private.audit_row() returns trigger
language plpgsql security definer set search_path = '' as $$
declare payload jsonb; actor uuid;
begin
  if current_setting('app.account_deletion', true) = '1' then return coalesce(new, old); end if;
  payload := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  actor := coalesce(auth.uid(), nullif(payload->>'user_id','')::uuid);
  if actor is not null then
    insert into public.audit_events(user_id, action, table_name, row_id)
    values(actor, lower(tg_op), tg_table_name, payload->>'id');
  end if;
  return coalesce(new, old);
end $$;
revoke all on function private.audit_row() from public, anon, authenticated;

create or replace function public.delete_own_account() returns void
language plpgsql security definer set search_path = '' as $$
declare account_id uuid := auth.uid();
begin
  if account_id is null then raise exception 'authentication required'; end if;
  perform set_config('app.account_deletion','1',true);
  delete from auth.sessions where user_id=account_id;
  delete from auth.users where id=account_id;
end $$;
revoke all on function public.delete_own_account() from public, anon;
grant execute on function public.delete_own_account() to authenticated;
