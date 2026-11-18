import { useState } from 'react'
type Relation = { restriccion: string; tabla_origen: string; tabla_destino: string; columnas_origen: string[]; columnas_destino: string[] }
type Entity = { nombre_completo: string; claves_primarias: string[][] }

function lines(value: string) {
  return value.match(/.{1,34}/gu) ?? ['']
}

export default function ObservedRelations({ relations, entities = [] }: { relations: Relation[]; entities?: Entity[] }) {
  const [visible, setVisible] = useState(25)
  const [visibleRelations, setVisibleRelations] = useState(20)
  return <section className="mb-4 rounded-lg border border-[#e1e7f0] bg-white p-3">
    <h4 className="text-sm font-semibold text-[#263d64]">Relaciones FK observadas</h4>
    <p className="mt-1 text-xs leading-5 text-[#687b99]">Cada flecha une una tabla que declara la FK con su tabla referenciada. No representa cardinalidad empresarial ni relaciones sin FK.</p>
    {entities.length > 0 && <>
      <p className="mt-3 text-xs text-[#687b99]">Entidades físicas y PK declaradas. Se incluyen las tablas sin relaciones.</p>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">{entities.slice(0, visible).map(entity => <div key={entity.nombre_completo} className="rounded-lg border border-[#d6dfec] bg-[#edf3ff] p-3 text-xs leading-5 break-words">
        <strong>{entity.nombre_completo}</strong><p>PK: {entity.claves_primarias.length ? entity.claves_primarias.map(key => key.join(', ')).join('; ') : 'Sin PK declarada'}</p>
      </div>)}</div>
      {visible < entities.length && <button type="button" onClick={() => setVisible(n => n+25)} className="mt-2 text-xs text-[#42618e] underline">Mostrar más entidades ({visible} de {entities.length})</button>}
    </>}
    {relations.slice(0, visibleRelations).map((relation, index) => {
      const source = [...lines(relation.tabla_origen), ...lines(`(${relation.columnas_origen.join(', ')})`)]
      const target = [...lines(relation.tabla_destino), ...lines(`(${relation.columnas_destino.join(', ')})`)]
      const height = Math.max(source.length, target.length) * 15 + 25
      return <div key={`${relation.restriccion}-${index}`} className="mt-3 overflow-x-auto" tabIndex={0} role="region" aria-label={`Relación ${relation.restriccion}`}>
        <p className="mb-1 text-xs break-words text-[#687b99]">{relation.restriccion}</p>
        <svg role="img" aria-label={`${relation.tabla_origen} referencia a ${relation.tabla_destino}`} viewBox={`0 0 650 ${height}`} className="min-w-[600px] w-full text-[#263d64]">
          <rect x="1" y="1" width="280" height={height - 2} rx="6" fill="#edf3ff" stroke="#d6dfec" />
          <rect x="369" y="1" width="280" height={height - 2} rx="6" fill="#edf3ff" stroke="#d6dfec" />
          <path d={`M282 ${height / 2}H365m-7-5 7 5-7 5`} fill="none" stroke="#42618e" strokeWidth="1.5" />
          {source.map((line, i) => <text key={i} x="12" y={22 + i * 15} fontSize="12" fill="currentColor">{line}</text>)}
          {target.map((line, i) => <text key={i} x="380" y={22 + i * 15} fontSize="12" fill="currentColor">{line}</text>)}
        </svg>
      </div>
    })}
    {relations.length > visibleRelations && <button type="button" onClick={() => setVisibleRelations(n => n+20)} className="mt-2 text-xs text-[#42618e] underline">Mostrar más relaciones ({visibleRelations} de {relations.length})</button>}
  </section>
}
