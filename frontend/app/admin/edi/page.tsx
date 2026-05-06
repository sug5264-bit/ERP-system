"use client";
import { useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import DataTable from "@/components/DataTable";
import Pager from "@/components/Pager";
import { Page, api } from "@/lib/api";

type EDI = {
  id: number;
  direction: "inbound" | "outbound";
  msg_type: string;
  partner_code: string | null;
  payload: string;
  payload_format: string;
  status: "received" | "parsed" | "processed" | "failed" | "sent";
  error: string | null;
  related_resource_type: string | null;
  related_resource_id: number | null;
  created_at: string;
};

const STATUS_COLOR: Record<string, string> = {
  received: "bg-blue-100 text-blue-700",
  parsed: "bg-slate-100 text-slate-700",
  processed: "bg-brand-100 text-brand-800",
  failed: "bg-red-100 text-red-700",
  sent: "bg-amber-100 text-amber-700",
};

export default function EDIPage() {
  const [messages, setMessages] = useState<EDI[]>([]);
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1 });
  const [error, setError] = useState("");
  const [showJson, setShowJson] = useState<EDI | null>(null);
  const [example, setExample] = useState(
    JSON.stringify(
      {
        msg_type: "PO",
        partner_code: "PARTNER-X",
        payload: {
          customer_code: "PARTNER-X",
          customer_name: "Partner X Co",
          order_no: "EDI-SO-099",
          items: [{ sku: "WG-COLA-355", qty: 50, unit_price: 1500 }],
        },
      },
      null,
      2
    )
  );

  const load = () =>
    api<Page<EDI>>(`/api/edi/messages?page=${page}&size=20`)
      .then((r) => {
        setMessages(r.items);
        setMeta({ total: r.total, pages: r.pages });
      })
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [page]);

  const submit = async () => {
    setError("");
    try {
      await api("/api/edi/inbound", { method: "POST", body: example });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  const process = async (id: number) => {
    try {
      await api(`/api/edi/messages/${id}/process`, { method: "POST" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <AppShell>
      <h1 className="text-2xl font-semibold mb-4">EDI / B2B 메시지</h1>

      <div className="bg-white p-4 rounded-lg border border-slate-200 mb-6 space-y-3">
        <h2 className="font-medium">테스트: 인바운드 메시지 전송</h2>
        <textarea
          value={example}
          onChange={(e) => setExample(e.target.value)}
          className="w-full font-mono text-xs border rounded p-2 h-48"
        />
        <button
          onClick={submit}
          className="px-4 py-2 bg-brand-700 text-white rounded text-sm"
        >
          /api/edi/inbound 호출
        </button>
        <p className="text-xs text-slate-500">
          partners 는 보통 X-API-Key를 사용해 직접 호출합니다. 위 폼은 사람이 시뮬레이션 용도.
        </p>
      </div>

      {error && <p className="text-red-600 text-sm mb-3">{error}</p>}

      <DataTable<EDI>
        columns={[
          { key: "id", header: "ID" },
          {
            key: "created_at",
            header: "시간",
            render: (m) => new Date(m.created_at).toLocaleString(),
          },
          {
            key: "direction",
            header: "방향",
            render: (m) => (m.direction === "inbound" ? "↓ in" : "↑ out"),
          },
          { key: "msg_type", header: "타입" },
          { key: "partner_code", header: "파트너" },
          {
            key: "status",
            header: "상태",
            render: (m) => (
              <span
                className={`px-2 py-0.5 rounded text-xs uppercase ${STATUS_COLOR[m.status] || ""}`}
              >
                {m.status}
              </span>
            ),
          },
          {
            key: "related",
            header: "연동 리소스",
            render: (m) =>
              m.related_resource_type
                ? `${m.related_resource_type}#${m.related_resource_id}`
                : "-",
          },
          {
            key: "actions",
            header: "",
            render: (m) => (
              <div className="flex gap-2">
                <button
                  onClick={() => setShowJson(m)}
                  className="text-xs text-blue-700 hover:underline"
                >
                  JSON
                </button>
                {m.direction === "inbound" && m.status === "received" && (
                  <button
                    onClick={() => process(m.id)}
                    className="text-xs text-brand-700 hover:underline"
                  >
                    처리
                  </button>
                )}
              </div>
            ),
          },
        ]}
        rows={messages}
      />
      <Pager page={page} pages={meta.pages} total={meta.total} onChange={setPage} />

      {showJson && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-30">
          <div className="bg-white rounded-lg p-6 w-[40rem] max-h-[80vh] overflow-y-auto space-y-3">
            <div className="flex justify-between items-center">
              <h2 className="font-medium">EDI #{showJson.id} payload</h2>
              <button onClick={() => setShowJson(null)} className="text-slate-500">✕</button>
            </div>
            {showJson.error && (
              <div className="bg-red-50 border border-red-200 rounded p-2 text-sm text-red-700">
                {showJson.error}
              </div>
            )}
            <pre className="bg-slate-100 p-3 rounded text-xs whitespace-pre-wrap overflow-x-auto">
              {(() => {
                try {
                  return JSON.stringify(JSON.parse(showJson.payload), null, 2);
                } catch {
                  return showJson.payload;
                }
              })()}
            </pre>
          </div>
        </div>
      )}
    </AppShell>
  );
}
