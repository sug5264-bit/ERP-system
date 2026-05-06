"use client";
import { useEffect, useRef, useState } from "react";
import { api, downloadFile, uploadFile } from "@/lib/api";

type Attachment = {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
};

export default function Attachments({
  relatedType,
  relatedId,
  canDelete = false,
}: {
  relatedType: string;
  relatedId: number;
  canDelete?: boolean;
}) {
  const [items, setItems] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api<Attachment[]>(
      `/api/attachments?related_type=${encodeURIComponent(relatedType)}&related_id=${relatedId}`
    )
      .then(setItems)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [relatedType, relatedId]);

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await uploadFile("/api/attachments", file, {
        related_type: relatedType,
        related_id: relatedId,
      });
      if (fileRef.current) fileRef.current.value = "";
      await load();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm("Delete this attachment?")) return;
    try {
      await api(`/api/attachments/${id}`, { method: "DELETE" });
      await load();
    } catch (e) {
      setError(String(e));
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          onChange={onUpload}
          disabled={busy}
          className="text-sm"
        />
        {busy && <span className="text-xs text-slate-500">업로드 중...</span>}
      </div>
      {error && <p className="text-red-600 text-xs">{error}</p>}
      {items.length === 0 ? (
        <p className="text-xs text-slate-500">첨부파일 없음</p>
      ) : (
        <ul className="text-sm space-y-1">
          {items.map((a) => (
            <li
              key={a.id}
              className="flex items-center justify-between px-2 py-1 bg-slate-50 rounded"
            >
              <button
                onClick={() => downloadFile(`/api/attachments/${a.id}/download`, a.filename)}
                className="text-blue-700 hover:underline truncate"
              >
                {a.filename}
              </button>
              <span className="text-xs text-slate-500">
                {(a.size / 1024).toFixed(1)} KB
                {canDelete && (
                  <button
                    onClick={() => onDelete(a.id)}
                    className="ml-3 text-red-600 hover:underline"
                  >
                    삭제
                  </button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
