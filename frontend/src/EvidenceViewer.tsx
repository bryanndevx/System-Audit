import { Fragment, useId, useState } from 'react'
import { humanizeKey } from './auditPresentation'
import ObservedRelations from './ObservedRelations'

type Primitive = string | number | boolean | null
type RecordValue = Record<string, unknown>

const INITIAL_VISIBLE_ROWS = 25
const VISIBLE_ROWS_INCREMENT = 25
const enumLabels: Record<string, string> = {
  catalogo_parametria: 'Catálogo / parametría', maestra: 'Maestra', transaccional: 'Transaccional', auditoria: 'Auditoría',
  temporal_staging: 'Temporal / staging', indeterminada: 'Indeterminada', sustentada_por_indicios: 'Sustentada por indicios',
  sin_indicios_suficientes: 'Sin indicios suficientes', indicios_ambiguos: 'Indicios ambiguos', heredada_de_padre: 'Heredada del padre',
  probable: 'Probable', tabla_ordinaria: 'Tabla ordinaria', tabla_particionada: 'Tabla particionada', tabla_externa: 'Tabla externa',
  parcial: 'Parcial', completa: 'Completa', no_evaluada: 'No evaluada',
  requiere_informacion_externa: 'Requiere información externa', obtenido: 'Obtenido', no_obtenido: 'No obtenido',
}
const enumFields = new Set(['clasificacion_tecnica', 'nivel_sustento', 'tipo', 'tipo_tabla', 'estado', 'cobertura_entregable'])

function isRecord(value: unknown): value is RecordValue {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isPrimitive(value: unknown): value is Primitive {
  return value === null || ['string', 'number', 'boolean'].includes(typeof value)
}

function isCompactValue(value: unknown): value is Primitive | Primitive[] {
  return isPrimitive(value) || (Array.isArray(value) && value.every(isPrimitive))
}

function formatNumber(value: number, key?: string) {
  const exactValue = new Intl.NumberFormat('es-CO').format(value)
  if (key?.endsWith('_bytes')) {
    const mebibytes = value / (1024 * 1024)
    return `${exactValue} B (${mebibytes.toLocaleString('es-CO', {
      maximumFractionDigits: 2,
    })} MiB)`
  }
  return exactValue
}

function PrimitiveValue({ value, field }: { value: Primitive; field?: string }) {
  if (value === null) {
    return <span className="text-[#8a9ab1]">No disponible</span>
  }
  if (typeof value === 'boolean') {
    return <span>{value ? 'Sí' : 'No'}</span>
  }
  if (typeof value === 'number') {
    return <span>{formatNumber(value, field)}</span>
  }
  if (!value) {
    return <span className="text-[#8a9ab1]">Vacío</span>
  }
  return <span className="whitespace-pre-wrap [overflow-wrap:anywhere]">{field && enumFields.has(field) ? enumLabels[value] ?? value : value}</span>
}

function CompactValue({
  value,
  field,
}: {
  value: Primitive | Primitive[]
  field?: string
}) {
  if (!Array.isArray(value)) return <PrimitiveValue value={value} field={field} />
  if (value.length === 0) return <span className="text-[#8a9ab1]">Sin elementos</span>
  const items = (
    <span className="leading-5 [overflow-wrap:anywhere]">
      {value.map((item, index) => (
        <Fragment key={index}>
          {index > 0 && <span className="text-[#8a9ab1]">; </span>}
          <PrimitiveValue value={item} field={field} />
        </Fragment>
      ))}
    </span>
  )
  if (value.length <= 3) return items
  return (
    <details>
      <summary className="w-fit cursor-pointer rounded font-medium text-[#42618e] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">{value.length} elementos</summary>
      <div className="mt-1.5">{items}</div>
    </details>
  )
}

function EvidenceTable({ records, depth }: { records: RecordValue[]; depth: number }) {
  const [visibleRows, setVisibleRows] = useState(INITIAL_VISIBLE_ROWS)
  const [expandedRows, setExpandedRows] = useState<Set<number>>(() => new Set())
  const tableId = useId()
  const allColumns = [...new Set(records.flatMap((record) => Object.keys(record)))]
  const compactColumns = allColumns.filter((column) => records.some((record) => isCompactValue(record[column])))
  const preferred = ['nombre_completo', 'campo', 'parametro', 'valor', 'rol', 'restriccion', 'clasificacion_tecnica', 'nivel_sustento', 'estado', 'validada', 'registros_huerfanos', 'tipo']
  const ordered = compactColumns.length > 5
    ? [...preferred.filter((column) => compactColumns.includes(column)), ...compactColumns.filter((column) => !preferred.includes(column))]
    : compactColumns
  const columns = ordered.slice(0, compactColumns.length > 5 ? 4 : 5)
  const emptyStructure = allColumns.length === 0
  const hasNestedData = records.some((record) => Object.entries(record).some(([key, value]) => !columns.includes(key) || !isCompactValue(value)))
  const numericColumns = new Set(columns.filter((column) =>
    records.some((record) => typeof record[column] === 'number') &&
    records.every((record) => record[column] == null || typeof record[column] === 'number'),
  ))
  const displayedRecords = records.slice(0, visibleRows)
  const remaining = records.length - displayedRecords.length
  const columnCount = columns.length + 1 + Number(hasNestedData) + Number(emptyStructure)

  const toggleRow = (index: number) => {
    setExpandedRows((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  return (
    <div>
      <div tabIndex={0} role="region" aria-label="Tabla de evidencia; puede desplazarse para ver todas las columnas" className="max-h-[26rem] overflow-auto overscroll-contain rounded-lg border border-[#e1e7f0] bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">
        <table className="w-full border-collapse text-left text-xs">
          <caption className="sr-only">Registros de evidencia técnica</caption>
          <thead className="sticky top-0 z-10 bg-[#f1f5fb] text-[#536984]">
            <tr>
              <th scope="col" className="w-9 px-2 py-2 text-right font-medium">#</th>
              {columns.map((column) => (
                <th scope="col" key={column} className={`min-w-28 max-w-56 px-2.5 py-2 leading-4 font-semibold ${numericColumns.has(column) ? 'text-right' : ''}`}>{humanizeKey(column)}</th>
              ))}
              {emptyStructure && <th scope="col" className="px-2.5 py-2 font-semibold">Contenido</th>}
              {hasNestedData && <th scope="col" className="sticky right-0 bg-[#f1f5fb] px-2.5 py-2 font-semibold">Detalle</th>}
            </tr>
          </thead>
          <tbody>
            {displayedRecords.map((record, rowIndex) => {
              const nested = Object.fromEntries(Object.entries(record).filter(([key, value]) => !columns.includes(key) || !isCompactValue(value)))
              const nestedCount = Object.keys(nested).length
              const expanded = expandedRows.has(rowIndex)
              const detailsId = `${tableId}-row-${rowIndex}`
              return (
                <Fragment key={rowIndex}>
                  <tr className={`border-t border-[#edf1f7] ${rowIndex % 2 ? 'bg-[#f8faff]' : 'bg-white'} hover:bg-[#edf3ff]/60`}>
                    <td className="px-2 py-2 text-right align-top leading-5 text-[#8a9ab1] tabular-nums">{rowIndex + 1}</td>
                    {columns.map((column) => {
                      const value = record[column]
                      return (
                        <td key={column} className={`min-w-28 max-w-56 px-2.5 py-2 align-top leading-5 text-[#536984] ${numericColumns.has(column) ? 'text-right tabular-nums' : ''}`}>
                          {value === undefined ? <span className="text-[#8a9ab1]">No informado</span> : isCompactValue(value) ? (
                            <CompactValue value={value} field={column} />
                          ) : <span className="text-[#8a9ab1]">Ver detalle</span>}
                        </td>
                      )
                    })}
                    {emptyStructure && <td className="px-2.5 py-2 text-[#8a9ab1]">Sin parámetros</td>}
                    {hasNestedData && <td className="sticky right-0 border-l border-[#edf1f7] bg-white px-2.5 py-2 align-top leading-5">
                      {nestedCount > 0 ? <button type="button" aria-expanded={expanded} aria-controls={expanded ? detailsId : undefined} aria-label={`${expanded ? 'Ocultar' : 'Ver'} detalles del registro ${rowIndex + 1}`} onClick={() => toggleRow(rowIndex)} className="inline-flex items-center gap-1 whitespace-nowrap rounded font-medium text-[#42618e] hover:text-[#263d64] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">
                        <svg aria-hidden="true" viewBox="0 0 16 16" className={`h-3 w-3 fill-none stroke-current stroke-[1.5] ${expanded ? 'rotate-90' : ''}`}><path d="m6 4 4 4-4 4" /></svg>
                        {expanded ? 'Ocultar' : 'Ver detalles'}
                      </button> : <span className="text-[#8a9ab1]">—</span>}
                    </td>}
                  </tr>
                  {expanded && nestedCount > 0 && <tr id={detailsId} className="border-t border-[#e1e7f0] bg-[#f4f7fb]">
                    <td colSpan={columnCount} className="p-3">
                      <p className="mb-2 text-[11px] font-semibold tracking-wide text-[#687b99] uppercase">Detalle del registro {rowIndex + 1}</p>
                      <EvidenceObject value={nested} depth={depth + 1} />
                    </td>
                  </tr>}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-[#687b99]">
        <span>Mostrando {displayedRecords.length} de {records.length} registros.</span>
        {remaining > 0 && (
          <button type="button" onClick={() => setVisibleRows((current) => Math.min(current + VISIBLE_ROWS_INCREMENT, records.length))} className="rounded-md border border-[#dce5f2] bg-white px-3 py-1.5 font-medium text-[#42618e] hover:bg-[#eef3fb] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#3568ec]">
            Mostrar {Math.min(VISIBLE_ROWS_INCREMENT, remaining)} más
          </button>
        )}
      </div>
    </div>
  )
}

function EvidenceArray({ values, depth }: { values: unknown[]; depth: number }) {
  if (values.length === 0) {
    return <p className="rounded-md bg-white px-3 py-2 text-sm text-[#8a9ab1]">Sin elementos.</p>
  }
  if (values.every(isRecord)) {
    return <EvidenceTable records={values as RecordValue[]} depth={depth} />
  }
  return <EvidenceTable records={values.map((value) => ({ valor: value }))} depth={depth} />
}

function EvidenceObject({ value, depth }: { value: RecordValue; depth: number }) {
  const entries = Object.entries(value)
  if (entries.length === 0) {
    return <p className="rounded-md bg-white px-3 py-2 text-sm text-[#8a9ab1]">Sin parámetros.</p>
  }
  const compactEntries = entries.filter(([, item]) => isCompactValue(item))
  const nestedEntries = entries.filter(([, item]) => !isCompactValue(item))
  const entities = Array.isArray(value.diagrama_er_fisico) ? value.diagrama_er_fisico.filter((item) => isRecord(item) && typeof item.nombre_completo === 'string' && Array.isArray(item.claves_primarias) && item.claves_primarias.every(key => Array.isArray(key) && key.every(column => typeof column === 'string'))) as { nombre_completo: string; claves_primarias: string[][] }[] : []
  const relations = Array.isArray(value.relaciones_fk) && value.relaciones_fk.every((item) => isRecord(item) && typeof item.restriccion === 'string' && typeof item.tabla_origen === 'string' && typeof item.tabla_destino === 'string' && Array.isArray(item.columnas_origen) && item.columnas_origen.every((column) => typeof column === 'string') && Array.isArray(item.columnas_destino) && item.columnas_destino.every((column) => typeof column === 'string'))
    ? value.relaciones_fk as { restriccion: string; tabla_origen: string; tabla_destino: string; columnas_origen: string[]; columnas_destino: string[] }[] : null

  return (
    <div className="space-y-4">
      {relations && (relations.length > 0 || entities.length > 0) && <ObservedRelations relations={relations} entities={entities} />}
      {compactEntries.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-[#e1e7f0] bg-white">
        <table className="w-full table-fixed border-collapse text-left text-xs">
          <caption className="sr-only">Parámetros y valores de evidencia</caption>
          <thead className="bg-[#f1f5fb] text-[#536984]"><tr><th scope="col" className="w-[48%] px-3 py-2 font-semibold">Parámetro</th><th scope="col" className="px-3 py-2 font-semibold">Valor</th></tr></thead>
          <tbody>
          {compactEntries.map(([key, item]) => (
            <tr key={key} className="border-t border-[#edf1f7] even:bg-[#f8faff]">
              <th scope="row" className="px-3 py-2 align-top leading-5 font-normal [overflow-wrap:anywhere] text-[#687b99]">{humanizeKey(key)}</th>
              <td className="px-3 py-2 align-top leading-5 text-[#263d64]">
                <CompactValue value={item as Primitive | Primitive[]} field={key} />
              </td>
            </tr>
          ))}
          </tbody>
        </table>
        </div>
      )}
      {nestedEntries.map(([key, item]) => (
        <section key={key} className="min-w-0">
          <h4 className="mb-2 text-xs font-semibold [overflow-wrap:anywhere] text-[#263d64]">{humanizeKey(key)}</h4>
          <EvidenceViewer value={item} depth={depth + 1} />
        </section>
      ))}
    </div>
  )
}

function EvidenceViewer({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (isPrimitive(value)) return <PrimitiveValue value={value} />
  if (Array.isArray(value)) return <EvidenceArray values={value} depth={depth} />
  if (isRecord(value)) return <EvidenceObject value={value} depth={depth} />
  return <span className="text-[#8a9ab1]">Formato de evidencia no disponible.</span>
}

export default EvidenceViewer
