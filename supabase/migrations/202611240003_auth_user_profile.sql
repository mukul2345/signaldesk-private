begin;

-- Runs as the database owner because auth.users is not writable by browser users.
-- It gives each newly created Auth user conservative paper-risk defaults.
create or replace function public.create_default_risk_settings()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.risk_settings(
    owner_id, capital, risk_per_trade_pct, max_open_positions, max_portfolio_risk_pct
  ) values (new.id, 50000, 1, 5, 5)
  on conflict (owner_id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.create_default_risk_settings();

commit;
