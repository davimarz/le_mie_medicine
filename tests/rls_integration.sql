-- Run with an administrative connection against a disposable/staging database.
-- Every change is rolled back. Any broken RLS assertion aborts the script.
begin;
insert into auth.users(id,email,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
values
 ('11111111-1111-4111-8111-111111111111','rls-owner@example.invalid','{}','{"username":"Owner"}',now(),now()),
 ('22222222-2222-4222-8222-222222222222','rls-caregiver@example.invalid','{}','{"username":"Caregiver"}',now(),now());
set local role authenticated;
select set_config('request.jwt.claims','{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}',true);
insert into public.farmaci(user_id,nome,quantita,tipo,scadenza)
values('11111111-1111-4111-8111-111111111111','RLS test',1,'Pezzi',current_date);
do $$ begin
 if (select count(*) from public.farmaci where nome='RLS test') <> 1 then raise exception 'owner read failed'; end if;
end $$;
select set_config('request.jwt.claims','{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}',true);
do $$ begin
 if (select count(*) from public.farmaci where nome='RLS test') <> 0 then raise exception 'cross-user read leak'; end if;
 update public.farmaci set nome='forbidden' where nome='RLS test';
 if found then raise exception 'cross-user update allowed'; end if;
end $$;
select set_config('request.jwt.claims','{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}',true);
select public.invite_caregiver('rls-caregiver@example.invalid','test');
select set_config('request.jwt.claims','{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}',true);
do $$ begin
 if (select count(*) from public.farmaci where nome='RLS test') <> 1 then raise exception 'caregiver read failed'; end if;
 update public.farmaci set nome='forbidden' where nome='RLS test';
 if found then raise exception 'caregiver update allowed'; end if;
end $$;
rollback;
