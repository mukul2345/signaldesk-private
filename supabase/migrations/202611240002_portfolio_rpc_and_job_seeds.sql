begin;

insert into public.scheduled_jobs(job_key, schedule, enabled) values
  ('daily-scan', '0 13 * * 1-5', false),
  ('paper-observation', '*/15 3-10 * * 1-5', false),
  ('portfolio-review', '30 10 * * 1-5', false),
  ('notification-delivery', '*/5 * * * *', false),
  ('retention', '0 19 * * 0', false)
on conflict (job_key) do nothing;

create or replace function public.record_portfolio_transaction(
  p_instrument_id uuid, p_side text, p_quantity numeric, p_price numeric,
  p_fees numeric, p_transacted_at timestamptz, p_idempotency_key text, p_notes text default null
) returns public.user_transactions
language plpgsql security invoker set search_path=public as $$
declare
  v_owner uuid := auth.uid();
  v_position public.user_positions;
  v_transaction public.user_transactions;
  v_new_quantity numeric;
begin
  if v_owner is null then raise exception 'authentication required'; end if;
  if p_side not in ('BUY','SELL') or p_quantity <= 0 or p_price <= 0 then
    raise exception 'invalid transaction';
  end if;
  select * into v_transaction from public.user_transactions where idempotency_key=p_idempotency_key;
  if found then return v_transaction; end if;
  select * into v_position from public.user_positions
    where owner_id=v_owner and instrument_id=p_instrument_id and status='OPEN' for update;
  if p_side='BUY' then
    if not found then
      insert into public.user_positions(owner_id,instrument_id,quantity,average_price)
        values(v_owner,p_instrument_id,p_quantity,p_price) returning * into v_position;
    else
      update public.user_positions set
        average_price=((quantity*average_price)+(p_quantity*p_price))/(quantity+p_quantity),
        quantity=quantity+p_quantity where id=v_position.id returning * into v_position;
    end if;
  else
    if not found or v_position.quantity < p_quantity then raise exception 'insufficient position quantity'; end if;
    v_new_quantity := v_position.quantity-p_quantity;
    update public.user_positions set quantity=v_new_quantity,
      status=case when v_new_quantity=0 then 'CLOSED' else 'OPEN' end,
      closed_at=case when v_new_quantity=0 then p_transacted_at else null end
      where id=v_position.id returning * into v_position;
  end if;
  insert into public.user_transactions(owner_id,position_id,instrument_id,side,quantity,price,fees,transacted_at,idempotency_key,notes)
    values(v_owner,v_position.id,p_instrument_id,p_side,p_quantity,p_price,greatest(p_fees,0),p_transacted_at,p_idempotency_key,p_notes)
    returning * into v_transaction;
  return v_transaction;
end $$;
grant execute on function public.record_portfolio_transaction(uuid,text,numeric,numeric,numeric,timestamptz,text,text) to authenticated;

commit;
