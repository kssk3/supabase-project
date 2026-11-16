# Shopping CRUD with Supabase

A Python command-line application for managing members, products, and orders in a Supabase PostgreSQL database. The project was initialized with uv. The CLI uses Python's standard library to call the Supabase Data API and prints the returned rows as JSON.

**Submission repository:** [kssk3/supabase-project](https://github.com/kssk3/supabase-project)

## Run locally

1. Install uv and use Python 3.11 or later. Clone the repository and open its directory.
2. For a fresh Supabase project, run [sql/schema.sql](sql/schema.sql) once in the SQL Editor. The script creates the three tables in one transaction. It has already been applied to the assignment project, `ax1_study`.
3. Run the following commands and fill in the project URL and server-side secret key in your local `.env`. The Data API must be enabled with the public schema exposed. The key is for a trusted local operator. Keep it out of browser code, screenshots, and Git.

```sh
uv sync --frozen
cp .env.example .env
# After editing .env:
uv run --frozen --env-file .env python -m shop --help
```

The examples below use this shell function as a shortcut:

```sh
shop() { uv run --frozen --env-file .env python -m shop "$@"; }
```

## Tables and relationships

```mermaid
erDiagram
    SHOP_MEMBERS ||--o{ SHOP_ORDERS : places
    SHOP_PRODUCTS ||--o{ SHOP_ORDERS : appears_in
    SHOP_MEMBERS {
        bigint id PK
        text email UK
    }
    SHOP_PRODUCTS {
        bigint id PK
        integer price
    }
    SHOP_ORDERS {
        bigint id PK
        bigint member_id FK
        bigint product_id FK
        integer quantity
        integer unit_price
    }
```

Every column is required (`NOT NULL` or a primary key). All three tables use database-generated IDs. Prices are integer Korean won (KRW).

| Table | Column | Type | Key, default, or rule |
| --- | --- | --- | --- |
| shop_members | id | bigint | PK, generated always as identity |
| shop_members | name | text | 1–100 characters after trimming |
| shop_members | email | text | Unique, basic email format |
| shop_members | phone | text | Defaults to empty text |
| shop_members | created_at | timestamptz | Defaults to now() |
| shop_products | id | bigint | PK, generated always as identity |
| shop_products | name | text | 1–100 characters after trimming |
| shop_products | price | integer | Current unit price, ≥ 0 |
| shop_products | stock | integer | ≥ 0, defaults to 0 |
| shop_products | description | text | Defaults to empty text |
| shop_products | created_at | timestamptz | Defaults to now() |
| shop_orders | id | bigint | PK, generated always as identity |
| shop_orders | member_id | bigint | FK → shop_members.id, ON DELETE RESTRICT |
| shop_orders | product_id | bigint | FK → shop_products.id, ON DELETE RESTRICT |
| shop_orders | quantity | integer | ≥ 1 |
| shop_orders | unit_price | integer | Unit price recorded at purchase, ≥ 0 |
| shop_orders | status | text | pending (default), paid, shipped, or cancelled |
| shop_orders | created_at | timestamptz | Defaults to now() |

Each order row represents one product purchased by one member. Either parent can appear in many orders. PostgreSQL blocks deleting a referenced member or product while an order still points to it. An order stores its own unit price, so changing the catalog price preserves the purchase price. The operator supplies the purchase price and manages stock separately. Row level security is enabled. The CLI uses a privileged server key, and anonymous and authenticated client roles have no direct table access.

## Try all twelve operations

Create a member and product first. Substitute their **returned IDs** for 1 and 2 below, then substitute the **returned order ID** for 3. Each table has its own ID sequence.

```sh
shop members create --name "Demo Member" --email demo@example.invalid
shop products create --name "Desk lamp" --price 18000 --stock 7
shop orders create --member-id 1 --product-id 2 --quantity 1 --unit-price 18000

shop members list --id 1
shop products list --id 2
shop orders list --id 3

shop members update 1 --name "Updated Member"
shop products update 2 --price 21000
shop orders update 3 --quantity 2

shop orders delete 3
shop products delete 2
shop members delete 1
```

Use `list` without `--id` to list rows. For example, `shop products list --limit 20 --offset 0` reads the first page in ascending ID order. A lookup after deletion returns `[]`. Updates and deletes on a missing ID return an error and exit with status 1.

## Live CRUD screenshots

The four screenshots below were captured directly in the **ax1_study Supabase SQL Editor** using Ego Lite. Each shows the SQL that ran and the result grid returned by the hosted database. The member, product, and order each received ID 2 in their respective tables during this run.

### Create

The first two inserts created Demo Kim and a Reading lamp. The third insert used the returned parent IDs to create a pending order for one lamp at 18,000 KRW.

![Supabase INSERT statements and the new order with its member and product IDs](docs/screenshots/create.png)

### Read

A separate SELECT joined the order to its member and product using both foreign keys. The result shows Demo Kim, Reading lamp, and a quantity of 1.

![Supabase SELECT joining the order to Demo Kim and the Reading lamp](docs/screenshots/read.png)

### Update

The three updates changed the member name to Demo Lee, the catalog price to 21,000 KRW, and the order quantity to 2. The result also shows that the recorded purchase price stayed at 18,000 KRW.

![Supabase UPDATE statements with the new member name, catalog price, and quantity beside the original purchase price](docs/screenshots/update.png)

### Delete

The transaction deleted the demo order before its referenced product and member. After the commit, a count for each demo ID returned zero.

![Supabase DELETE statements and a result grid showing zero remaining matches in all three tables](docs/screenshots/delete.png)

## Run the tests

```sh
uv run --frozen python -m unittest discover -s tests -v
```

The automated suite checks request construction, validation, and error handling using a simulated transport. It runs without Supabase credentials. The screenshots above document a separate run against the hosted database.
