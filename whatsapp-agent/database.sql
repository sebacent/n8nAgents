-- ============================================================
-- WHATSAPP AGENT - SUPABASE SCHEMA
-- Gastos y Comidas con soporte multi-usuario
-- ============================================================

-- Habilitar extensión UUID
create extension if not exists "pgcrypto";


-- ============================================================
-- TABLAS PRINCIPALES
-- ============================================================

create table if not exists gastos (
  id          uuid primary key default gen_random_uuid(),
  fecha       timestamptz default now(),
  usuario     text not null,
  descripcion text not null,
  categoria   text default 'otros',
  monto       numeric(10, 2) not null check (monto >= 0)
);

create table if not exists comidas (
  id        uuid primary key default gen_random_uuid(),
  fecha     timestamptz default now(),
  usuario   text not null,
  alimento  text not null,
  cantidad  text default '1 porción',
  calorias  int default 0 check (calorias >= 0)
);


-- ============================================================
-- ÍNDICES DE PERFORMANCE
-- ============================================================

-- Consultas por usuario y fecha (las más frecuentes)
create index if not exists idx_gastos_usuario_fecha   on gastos (usuario, fecha desc);
create index if not exists idx_comidas_usuario_fecha  on comidas (usuario, fecha desc);

-- Consultas por categoría (para reportes)
create index if not exists idx_gastos_categoria on gastos (categoria);

-- Consultas solo por fecha (reportes globales)
create index if not exists idx_gastos_fecha  on gastos (fecha desc);
create index if not exists idx_comidas_fecha on comidas (fecha desc);


-- ============================================================
-- VISTAS ÚTILES
-- ============================================================

-- Resumen diario de gastos por usuario
create or replace view resumen_gastos_diario as
select
  usuario,
  date_trunc('day', fecha at time zone 'America/Montevideo')::date as dia,
  categoria,
  count(*)         as cantidad_gastos,
  sum(monto)       as total_monto,
  avg(monto)       as promedio_monto
from gastos
group by usuario, dia, categoria
order by dia desc, total_monto desc;

-- Resumen diario de calorías por usuario
create or replace view resumen_calorias_diario as
select
  usuario,
  date_trunc('day', fecha at time zone 'America/Montevideo')::date as dia,
  count(*)       as cantidad_comidas,
  sum(calorias)  as total_calorias,
  avg(calorias)  as promedio_calorias
from comidas
group by usuario, dia
order by dia desc;

-- Vista combinada para dashboard
create or replace view dashboard_diario as
select
  coalesce(g.usuario, c.usuario)   as usuario,
  coalesce(g.dia, c.dia)           as dia,
  coalesce(g.total_gastos, 0)      as total_gastos_uyu,
  coalesce(c.total_calorias, 0)    as total_calorias_kcal,
  coalesce(g.cantidad_gastos, 0)   as cantidad_gastos,
  coalesce(c.cantidad_comidas, 0)  as cantidad_comidas
from (
  select
    usuario,
    date_trunc('day', fecha at time zone 'America/Montevideo')::date as dia,
    sum(monto) as total_gastos,
    count(*)   as cantidad_gastos
  from gastos
  group by usuario, dia
) g
full outer join (
  select
    usuario,
    date_trunc('day', fecha at time zone 'America/Montevideo')::date as dia,
    sum(calorias) as total_calorias,
    count(*)      as cantidad_comidas
  from comidas
  group by usuario, dia
) c on g.usuario = c.usuario and g.dia = c.dia
order by dia desc;

-- Top categorías de gastos (para análisis mensual)
create or replace view top_categorias_mensual as
select
  usuario,
  date_trunc('month', fecha at time zone 'America/Montevideo')::date as mes,
  categoria,
  count(*)     as cantidad,
  sum(monto)   as total,
  round(100.0 * sum(monto) / sum(sum(monto)) over (
    partition by usuario, date_trunc('month', fecha at time zone 'America/Montevideo')
  ), 1) as porcentaje
from gastos
group by usuario, mes, categoria
order by mes desc, total desc;


-- ============================================================
-- FUNCIONES RPC (para consultas desde n8n y apps futuras)
-- ============================================================

-- Resumen del día para un usuario específico
create or replace function get_resumen_dia(
  p_usuario text,
  p_fecha   date default current_date
)
returns json
language plpgsql
as $$
declare
  v_total_gastos   numeric;
  v_total_calorias int;
  v_gastos         json;
  v_comidas        json;
  v_tz             text := 'America/Montevideo';
begin
  select
    coalesce(sum(monto), 0),
    json_agg(json_build_object(
      'descripcion', descripcion,
      'categoria',   categoria,
      'monto',       monto,
      'hora',        to_char(fecha at time zone v_tz, 'HH24:MI')
    ) order by fecha desc)
  into v_total_gastos, v_gastos
  from gastos
  where usuario = p_usuario
    and (fecha at time zone v_tz)::date = p_fecha;

  select
    coalesce(sum(calorias), 0),
    json_agg(json_build_object(
      'alimento',  alimento,
      'cantidad',  cantidad,
      'calorias',  calorias,
      'hora',      to_char(fecha at time zone v_tz, 'HH24:MI')
    ) order by fecha desc)
  into v_total_calorias, v_comidas
  from comidas
  where usuario = p_usuario
    and (fecha at time zone v_tz)::date = p_fecha;

  return json_build_object(
    'fecha',           p_fecha,
    'usuario',         p_usuario,
    'total_gastos',    v_total_gastos,
    'total_calorias',  v_total_calorias,
    'gastos',          coalesce(v_gastos, '[]'::json),
    'comidas',         coalesce(v_comidas, '[]'::json)
  );
end;
$$;

-- Reporte quincenal (preparado para reportes automáticos)
create or replace function get_reporte_quincenal(
  p_usuario text,
  p_anio    int     default extract(year from current_date)::int,
  p_mes     int     default extract(month from current_date)::int,
  p_quincena int    default case when extract(day from current_date) <= 15 then 1 else 2 end
)
returns json
language plpgsql
as $$
declare
  v_fecha_inicio date;
  v_fecha_fin    date;
  v_tz           text := 'America/Montevideo';
begin
  if p_quincena = 1 then
    v_fecha_inicio := make_date(p_anio, p_mes, 1);
    v_fecha_fin    := make_date(p_anio, p_mes, 15);
  else
    v_fecha_inicio := make_date(p_anio, p_mes, 16);
    v_fecha_fin    := (make_date(p_anio, p_mes, 1) + interval '1 month - 1 day')::date;
  end if;

  return (
    select json_build_object(
      'periodo',        json_build_object('inicio', v_fecha_inicio, 'fin', v_fecha_fin, 'quincena', p_quincena),
      'usuario',        p_usuario,
      'gastos', json_build_object(
        'total',        coalesce(sum(g.monto), 0),
        'cantidad',     count(g.id),
        'por_categoria', (
          select json_agg(json_build_object('categoria', categoria, 'total', sum(monto), 'cantidad', count(*)))
          from gastos
          where usuario = p_usuario
            and (fecha at time zone v_tz)::date between v_fecha_inicio and v_fecha_fin
          group by categoria
          order by sum(monto) desc
        )
      ),
      'calorias', json_build_object(
        'total',        coalesce(sum(c.calorias), 0),
        'promedio_dia', coalesce(avg(c.calorias_dia), 0)
      )
    )
    from gastos g
    cross join lateral (
      select sum(calorias) as calorias, avg(sum_dia) as calorias_dia
      from (
        select sum(calorias) as sum_dia
        from comidas
        where usuario = p_usuario
          and (fecha at time zone v_tz)::date between v_fecha_inicio and v_fecha_fin
        group by (fecha at time zone v_tz)::date
      ) t
    ) c
    where g.usuario = p_usuario
      and (g.fecha at time zone v_tz)::date between v_fecha_inicio and v_fecha_fin
  );
end;
$$;


-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Para cuando se implemente autenticación Supabase Auth
-- ============================================================

-- Habilitar RLS en las tablas
alter table gastos  enable row level security;
alter table comidas enable row level security;

-- Política para service role (n8n usa service role → acceso total)
-- Con la service role key, el RLS no aplica por defecto en Supabase.
-- Estas políticas son para cuando se use anon key o authenticated users.

-- Política: cada usuario solo ve sus propios datos (para futuro dashboard)
create policy "usuarios ven sus gastos"  on gastos
  for all using (auth.uid()::text = usuario or current_role = 'service_role');

create policy "usuarios ven sus comidas" on comidas
  for all using (auth.uid()::text = usuario or current_role = 'service_role');


-- ============================================================
-- DATOS DE EJEMPLO (opcional, para testing)
-- ============================================================

-- Descomentar para insertar datos de prueba:
/*
insert into gastos (usuario, descripcion, categoria, monto) values
  ('5989123456', 'Café',           'comida',       120),
  ('5989123456', 'Uber al trabajo','transporte',   350),
  ('5989123456', 'Supermercado',   'hogar',       2500),
  ('5989123456', 'Nafta',          'transporte',   400);

insert into comidas (usuario, alimento, cantidad, calorias) values
  ('5989123456', 'Café con leche', '1 taza',   80),
  ('5989123456', 'Tostadas',       '2 rebanadas', 160),
  ('5989123456', 'Pizza',          '2 porciones', 560),
  ('5989123456', 'Manzana',        '1 unidad',    80);
*/
