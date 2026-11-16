-- Run once in the Supabase SQL Editor. Existing tables are never dropped.
begin;

create table public.shop_members (
    id bigint generated always as identity primary key,
    name text not null check (length(btrim(name)) between 1 and 100),
    email text not null unique check (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    phone text not null default '',
    created_at timestamptz not null default now()
);

create table public.shop_products (
    id bigint generated always as identity primary key,
    name text not null check (length(btrim(name)) between 1 and 100),
    price integer not null check (price >= 0),
    stock integer not null default 0 check (stock >= 0),
    description text not null default '',
    created_at timestamptz not null default now()
);

-- One order represents one product line; unit_price is the price at purchase.
create table public.shop_orders (
    id bigint generated always as identity primary key,
    member_id bigint not null references public.shop_members(id) on delete restrict,
    product_id bigint not null references public.shop_products(id) on delete restrict,
    quantity integer not null check (quantity > 0),
    unit_price integer not null check (unit_price >= 0),
    status text not null default 'pending' check (status in ('pending', 'paid', 'shipped', 'cancelled')),
    created_at timestamptz not null default now()
);

create index shop_orders_member_id_idx on public.shop_orders(member_id);
create index shop_orders_product_id_idx on public.shop_orders(product_id);

alter table public.shop_members enable row level security;
alter table public.shop_products enable row level security;
alter table public.shop_orders enable row level security;

-- This assignment is a trusted local operator CLI, not a public web client.
-- No anon/authenticated policies: browser clients cannot read or mutate the data.
revoke all on public.shop_members, public.shop_products, public.shop_orders from anon, authenticated;
grant select, insert, update, delete on public.shop_members, public.shop_products, public.shop_orders to service_role;
revoke all on sequence public.shop_members_id_seq, public.shop_products_id_seq, public.shop_orders_id_seq from anon, authenticated;
grant usage, select on sequence public.shop_members_id_seq, public.shop_products_id_seq, public.shop_orders_id_seq to service_role;

commit;
