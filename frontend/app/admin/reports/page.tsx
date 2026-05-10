"use client";
import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { api } from "@/lib/api";
import { hasRole, useMe } from "@/lib/auth";

type DataSources = Record<string, string[]>;
type Aggregate = "count" | "sum" | "avg" | "min" | "max";
type FilterOp = "eq" | "ne" | "gt" | "gte" | "lt" | "lte" | "like" | "in";

type Spec = {
  data_source: string;
  columns: (string | { agg: Aggregate; column: string; alias?: string })[];
  filters: { column: string; op: FilterOp; value: any }[];
  group_by: string[];
  order_by: { column: string; dir: "asc" | "desc" }[];
  limit: number;
};

type Definition = {
  id: number;
  code: string;
  name: string;
  description: string | null;
  spec: Spec;
  is_public: boolean;
  owner_id: number | null;
};

type RunResult = { columns: string[]; rows: any[]; count: number };

const AGGS: Aggregate[] = ["count", "sum", "avg", "min", "max"];
const OPS: FilterOp[] = ["eq", "ne", "gt", "gte", "lt", "lte", "like", "in"];

export default function ReportBuilderPage() {
  const me = useMe();
  const isAdmin = hasRole(me, "admin");

  const [sources, setSources] = useState<DataSources>({});
  const [defs, setDefs] = useState<Definition[]>([]);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);

  const [spec, setSpec] = useState<Spec>({
    data_source: "",
    columns: [],
    filters: [],
    group_by: [],
    order_by: [],
    limit: 100,
  });

  const cols = useMemo(
    () => sources[spec.data_source] || [],
    [sources, spec.data_source]
  );

  const [save, setSave] = useState({
    code: "",
    name: "",
    description: "",
    is_public: false,
  });

  const loadDefs = async () => {
    try {
      setDefs(await api<Definition[]>("/api/report-builder/definitions"));
    } catch (e) {
      setError(String(e));
    }
  };

  useEffect(() => {
    (async () => {
      try {
        setSources(await api<DataSources>("/api/report-builder/data-sources"));
      } catch (e) {
        setError(String(e));
      }
    })();
    loadDefs();
  }, []);

  const run = async () => {
    setError("");
    setResult(null);
    try {
      setResult(
        await api<RunResult>("/api/report-builder/run", {
          method: "POST",
          body: JSON.stringify(spec),
        })
      );
    } catch (e) {
      setError(String(e));
    }
  };

  const persist = async () => {
    setError("");
    if (!save.code || !save.name) {
      setError("코드/이름을 입력하세요");
      return;
    }
    try {
      await api("/api/report-builder/definitions", {
        method: "POST",
        body: JSON.stringify({
          code: save.code,
          name: save.name,
          description: save.description || null,
          is_public: save.is_public,
          spec,
        }),
      });
      setSave({ code: "", name: "", description: "", is_public: false });
      await loadDefs();
    } catch (e) {
      setError(String(e));
    }
  };

  const loadDef = (d: Definition) => {
    setSpec({
      data_source: d.spec.data_source,
      columns: d.spec.columns || [],
      filters: d.spec.filters || [],
      group_by: d.spec.group_by || [],
      order_by: d.spec.order_by || [],
      limit: d.spec.limit || 100,
    });
  };

  const runSaved = async (id: number) => {
    setError("");
    try {
      setResult(
        await api<RunResult>(`/api/report-builder/definitions/${id}/run`)
      );
    } catch (e) {
      setError(String(e));
    }
  };

  const removeDef = async (id: number) => {
    if (!confirm("정의를 삭제하시겠습니까?")) return;
    try {
      await api(`/api/report-builder/definitions/${id}`, { method: "DELETE" });
      await loadDefs();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">리포트 빌더</h1>
      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Builder */}
        <div className="lg:col-span-2 bg-white p-4 rounded-lg shadow-sm border border-slate-200 space-y-4">
          <div>
            <label className="text-sm font-medium">데이터 소스</label>
            <select
              value={spec.data_source}
              onChange={(e) =>
                setSpec({ ...spec, data_source: e.target.value, columns: [], filters: [], group_by: [], order_by: [] })
              }
              className="border rounded px-2 py-1 ml-2"
            >
              <option value="">— 선택 —</option>
              {Object.keys(sources).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          {spec.data_source && (
            <>
              <div>
                <p className="text-sm font-medium mb-1">컬럼</p>
                {spec.columns.map((c, i) => (
                  <div key={i} className="flex gap-2 mb-1">
                    {typeof c === "string" ? (
                      <select
                        value={c}
                        onChange={(e) => {
                          const cs = [...spec.columns];
                          cs[i] = e.target.value;
                          setSpec({ ...spec, columns: cs });
                        }}
                        className="border rounded px-2 py-1"
                      >
                        {cols.map((co) => (
                          <option key={co} value={co}>
                            {co}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <>
                        <select
                          value={c.agg}
                          onChange={(e) => {
                            const cs = [...spec.columns];
                            cs[i] = { ...c, agg: e.target.value as Aggregate };
                            setSpec({ ...spec, columns: cs });
                          }}
                          className="border rounded px-2 py-1"
                        >
                          {AGGS.map((a) => (
                            <option key={a}>{a}</option>
                          ))}
                        </select>
                        <select
                          value={c.column}
                          onChange={(e) => {
                            const cs = [...spec.columns];
                            cs[i] = { ...c, column: e.target.value };
                            setSpec({ ...spec, columns: cs });
                          }}
                          className="border rounded px-2 py-1"
                        >
                          {cols.map((co) => (
                            <option key={co}>{co}</option>
                          ))}
                        </select>
                        <input
                          placeholder="alias"
                          value={c.alias || ""}
                          onChange={(e) => {
                            const cs = [...spec.columns];
                            cs[i] = { ...c, alias: e.target.value };
                            setSpec({ ...spec, columns: cs });
                          }}
                          className="border rounded px-2 py-1"
                        />
                      </>
                    )}
                    <button
                      type="button"
                      onClick={() =>
                        setSpec({
                          ...spec,
                          columns: spec.columns.filter((_, j) => j !== i),
                        })
                      }
                      className="text-red-600 text-xs"
                    >
                      삭제
                    </button>
                  </div>
                ))}
                <div className="flex gap-2 mt-1">
                  <button
                    type="button"
                    onClick={() =>
                      setSpec({ ...spec, columns: [...spec.columns, cols[0]] })
                    }
                    className="text-xs text-blue-700"
                  >
                    + 컬럼
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setSpec({
                        ...spec,
                        columns: [
                          ...spec.columns,
                          { agg: "count", column: cols[0] },
                        ],
                      })
                    }
                    className="text-xs text-blue-700"
                  >
                    + 집계
                  </button>
                </div>
              </div>

              <div>
                <p className="text-sm font-medium mb-1">필터</p>
                {spec.filters.map((f, i) => (
                  <div key={i} className="flex gap-2 mb-1">
                    <select
                      value={f.column}
                      onChange={(e) => {
                        const fs = [...spec.filters];
                        fs[i] = { ...f, column: e.target.value };
                        setSpec({ ...spec, filters: fs });
                      }}
                      className="border rounded px-2 py-1"
                    >
                      {cols.map((co) => (
                        <option key={co}>{co}</option>
                      ))}
                    </select>
                    <select
                      value={f.op}
                      onChange={(e) => {
                        const fs = [...spec.filters];
                        fs[i] = { ...f, op: e.target.value as FilterOp };
                        setSpec({ ...spec, filters: fs });
                      }}
                      className="border rounded px-2 py-1"
                    >
                      {OPS.map((o) => (
                        <option key={o}>{o}</option>
                      ))}
                    </select>
                    <input
                      value={f.value ?? ""}
                      onChange={(e) => {
                        const fs = [...spec.filters];
                        fs[i] = { ...f, value: e.target.value };
                        setSpec({ ...spec, filters: fs });
                      }}
                      className="border rounded px-2 py-1 flex-1"
                    />
                    <button
                      type="button"
                      onClick={() =>
                        setSpec({
                          ...spec,
                          filters: spec.filters.filter((_, j) => j !== i),
                        })
                      }
                      className="text-red-600 text-xs"
                    >
                      삭제
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() =>
                    setSpec({
                      ...spec,
                      filters: [
                        ...spec.filters,
                        { column: cols[0], op: "eq", value: "" },
                      ],
                    })
                  }
                  className="text-xs text-blue-700"
                >
                  + 필터
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <p className="text-sm font-medium mb-1">Group By</p>
                  {spec.group_by.map((g, i) => (
                    <div key={i} className="flex gap-2 mb-1">
                      <select
                        value={g}
                        onChange={(e) => {
                          const gs = [...spec.group_by];
                          gs[i] = e.target.value;
                          setSpec({ ...spec, group_by: gs });
                        }}
                        className="border rounded px-2 py-1 flex-1"
                      >
                        {cols.map((co) => (
                          <option key={co}>{co}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        onClick={() =>
                          setSpec({
                            ...spec,
                            group_by: spec.group_by.filter((_, j) => j !== i),
                          })
                        }
                        className="text-red-600 text-xs"
                      >
                        삭제
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      setSpec({ ...spec, group_by: [...spec.group_by, cols[0]] })
                    }
                    className="text-xs text-blue-700"
                  >
                    + 그룹
                  </button>
                </div>
                <div>
                  <p className="text-sm font-medium mb-1">Order By</p>
                  {spec.order_by.map((o, i) => (
                    <div key={i} className="flex gap-2 mb-1">
                      <select
                        value={o.column}
                        onChange={(e) => {
                          const os = [...spec.order_by];
                          os[i] = { ...o, column: e.target.value };
                          setSpec({ ...spec, order_by: os });
                        }}
                        className="border rounded px-2 py-1 flex-1"
                      >
                        {cols.map((co) => (
                          <option key={co}>{co}</option>
                        ))}
                      </select>
                      <select
                        value={o.dir}
                        onChange={(e) => {
                          const os = [...spec.order_by];
                          os[i] = {
                            ...o,
                            dir: e.target.value as "asc" | "desc",
                          };
                          setSpec({ ...spec, order_by: os });
                        }}
                        className="border rounded px-2 py-1"
                      >
                        <option value="asc">asc</option>
                        <option value="desc">desc</option>
                      </select>
                      <button
                        type="button"
                        onClick={() =>
                          setSpec({
                            ...spec,
                            order_by: spec.order_by.filter((_, j) => j !== i),
                          })
                        }
                        className="text-red-600 text-xs"
                      >
                        삭제
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() =>
                      setSpec({
                        ...spec,
                        order_by: [
                          ...spec.order_by,
                          { column: cols[0], dir: "asc" },
                        ],
                      })
                    }
                    className="text-xs text-blue-700"
                  >
                    + 정렬
                  </button>
                </div>
              </div>

              <div>
                <label className="text-sm">Limit</label>
                <input
                  type="number"
                  value={spec.limit}
                  onChange={(e) =>
                    setSpec({ ...spec, limit: Number(e.target.value) })
                  }
                  className="border rounded px-2 py-1 ml-2 w-24"
                />
              </div>

              <div className="flex gap-2">
                <button
                  onClick={run}
                  className="bg-emerald-700 text-white px-4 py-1 rounded"
                >
                  ▶ 실행
                </button>
              </div>

              <div className="border-t pt-3 space-y-2">
                <p className="text-sm font-medium">정의로 저장</p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <input
                    placeholder="코드"
                    value={save.code}
                    onChange={(e) => setSave({ ...save, code: e.target.value })}
                    className="border rounded px-2 py-1"
                  />
                  <input
                    placeholder="이름"
                    value={save.name}
                    onChange={(e) => setSave({ ...save, name: e.target.value })}
                    className="border rounded px-2 py-1"
                  />
                  <input
                    placeholder="설명"
                    value={save.description}
                    onChange={(e) =>
                      setSave({ ...save, description: e.target.value })
                    }
                    className="border rounded px-2 py-1"
                  />
                  <label className="flex items-center gap-1 text-sm">
                    <input
                      type="checkbox"
                      checked={save.is_public}
                      onChange={(e) =>
                        setSave({ ...save, is_public: e.target.checked })
                      }
                    />
                    공개
                  </label>
                </div>
                <button
                  onClick={persist}
                  className="bg-slate-900 text-white px-3 py-1 rounded text-sm"
                >
                  저장
                </button>
              </div>
            </>
          )}
        </div>

        {/* Saved definitions */}
        <div className="bg-white p-4 rounded-lg shadow-sm border border-slate-200">
          <h2 className="text-lg font-medium mb-2">저장된 리포트</h2>
          {defs.length === 0 && (
            <p className="text-sm text-slate-500">저장된 항목이 없습니다.</p>
          )}
          <ul className="space-y-2">
            {defs.map((d) => (
              <li key={d.id} className="border rounded p-2 text-sm">
                <div className="flex justify-between">
                  <div>
                    <div className="font-medium">{d.name}</div>
                    <div className="text-xs text-slate-500">
                      {d.code} {d.is_public && "· 공개"}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => loadDef(d)}
                      className="text-blue-700 text-xs"
                    >
                      불러오기
                    </button>
                    <button
                      onClick={() => runSaved(d.id)}
                      className="text-emerald-700 text-xs"
                    >
                      실행
                    </button>
                    {isAdmin && (
                      <button
                        onClick={() => removeDef(d.id)}
                        className="text-red-600 text-xs"
                      >
                        삭제
                      </button>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Result */}
      {result && (
        <div className="mt-4 bg-white p-4 rounded-lg shadow-sm border border-slate-200">
          <h2 className="text-lg font-medium mb-2">
            결과 ({result.count}행)
          </h2>
          <div className="overflow-auto">
            <table className="text-sm w-full">
              <thead>
                <tr className="bg-slate-100">
                  {result.columns.map((c) => (
                    <th key={c} className="px-2 py-1 text-left font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.map((r, i) => (
                  <tr key={i} className="border-t">
                    {result.columns.map((c) => (
                      <td key={c} className="px-2 py-1">
                        {r[c] === null || r[c] === undefined ? "-" : String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppShell>
  );
}
