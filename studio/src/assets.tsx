import { useCallback, useEffect, useState } from 'react';
import { ApiError, request } from './api';
import type { Source } from './editor-fields';
import type { AssetListing, AssetUse, LibraryAsset, TrashEntry } from './types';
import { Status } from './ui';

// The project's imported photographs and fonts, with every saved and draft use.
// Python decides whether an asset may be removed; removal moves it to the
// project's trash (restorable), and permanent deletion is a second, separate step.

function bytes(n: number) {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`;
}

function facts(asset: LibraryAsset): string {
  const f = asset.facts as Record<string, unknown>;
  if (asset.kind === 'photo') {
    const pixels = f.pixels as [number, number] | undefined;
    return [String(f.format ?? '').toUpperCase(), pixels ? `${pixels[0]} × ${pixels[1]} px` : '']
      .filter(Boolean)
      .join(' · ');
  }
  return [
    String(f.full_name ?? ''),
    f.embedding ? `embedding ${String(f.embedding).replace('_', ' ')}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
}

type Pending = { kind: 'trash'; asset: LibraryAsset } | { kind: 'purge'; entry: TrashEntry };

export function AssetsPanel({
  projectKey,
  draft,
  onShowUse,
  licenses,
}: {
  projectKey: string;
  draft: Source;
  onShowUse?: (use: AssetUse) => void;
  licenses?: Record<string, string | null | undefined>;
}) {
  const [listing, setListing] = useState<AssetListing>();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<'all' | 'photo' | 'font' | 'unused'>('all');
  const [pending, setPending] = useState<Pending | null>(null);
  const [message, setMessage] = useState('');
  const [blocked, setBlocked] = useState<{ name: string; uses: AssetUse[] } | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/api/projects/${encodeURIComponent(projectKey)}/assets`;
  const signature = JSON.stringify([draft.cover, draft.interior]);
  const load = useCallback(
    (signal: AbortSignal) =>
      request<AssetListing>(`${base}/list`, signal, { source: draft })
        .then((data) => !signal.aborted && setListing(data))
        .catch((err: Error) => !signal.aborted && setMessage(err.message)),
    // `signature` captures every draft value that can reference an asset.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, signature],
  );
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);
  const act = async (path: string, body: object, done: string) => {
    setBusy(true);
    setBlocked(null);
    try {
      const data = await request<AssetListing>(
        `${base}/${path}`,
        new AbortController().signal,
        body,
      );
      setListing(data);
      setMessage(done);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'asset_in_use') {
        setBlocked({ name: path, uses: err.uses });
      }
      setMessage(err instanceof Error ? err.message : 'The request did not complete.');
    } finally {
      setBusy(false);
      setPending(null);
    }
  };
  const needle = query.trim().toLowerCase();
  const shown = (listing?.assets ?? []).filter(
    (asset) =>
      (kind === 'all' || (kind === 'unused' ? !asset.in_use : asset.kind === kind)) &&
      (!needle ||
        asset.name.toLowerCase().includes(needle) ||
        (asset.sha256 ?? '').startsWith(needle)),
  );
  return (
    <div className="tool-section assets-panel">
      <div className="tool-heading">
        <h3>Assets</h3>
      </div>
      <p className="small muted">
        Imported photographs and fonts in this project. Identical files are stored once. An asset
        used by the saved book or this draft cannot be removed; removing moves it to the
        project&apos;s trash, where it can be restored.
      </p>
      <div className="navigator-filters">
        <label className="sr-only" htmlFor="asset-search">
          Search assets
        </label>
        <input
          id="asset-search"
          type="search"
          placeholder="Search name or SHA-256"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <label className="sr-only" htmlFor="asset-kind">
          Show
        </label>
        <select
          id="asset-kind"
          value={kind}
          onChange={(e) => setKind(e.target.value as typeof kind)}
        >
          <option value="all">All assets</option>
          <option value="photo">Photographs</option>
          <option value="font">Fonts</option>
          <option value="unused">Not in use</option>
        </select>
      </div>
      {!listing ? (
        <p className="small muted">Reading the project&apos;s assets…</p>
      ) : shown.length === 0 ? (
        <p className="small muted">No assets match.</p>
      ) : (
        <ul className="asset-list" aria-label="Project assets">
          {shown.map((asset) => (
            <li key={asset.path}>
              {asset.kind === 'photo' ? (
                <img
                  src={`/api/projects/${encodeURIComponent(projectKey)}/cover/assets/thumbnail?path=${encodeURIComponent(asset.path)}`}
                  alt=""
                  loading="lazy"
                />
              ) : (
                <img
                  className="font-specimen"
                  src={`/api/projects/${encodeURIComponent(projectKey)}/cover/fonts/specimen?font=${encodeURIComponent(asset.path)}`}
                  alt={`Specimen of ${asset.name}`}
                  loading="lazy"
                />
              )}
              <div className="asset-facts">
                <strong title={asset.path}>{asset.name}</strong>
                <span className="small muted">
                  {asset.kind === 'photo' ? 'Photograph' : 'Font'} · {facts(asset)} ·{' '}
                  {bytes(asset.bytes)}
                </span>
                {asset.sha256 && (
                  <code className="small identity" title={asset.sha256}>
                    SHA-256 {asset.sha256.slice(0, 16)}…
                  </code>
                )}
                {asset.kind === 'font' && licenses && (
                  <span className="small muted">
                    License:{' '}
                    {licenses[asset.path] ?? 'not recorded (you record it; it is not verified)'}
                  </span>
                )}
                {asset.problem && (
                  <span className="small field-errors">
                    Unusable: {asset.problem.replaceAll('_', ' ')}
                  </span>
                )}
                {asset.in_use ? (
                  <ul className="asset-uses small">
                    {asset.uses.map((use) => (
                      <li key={`${use.source}-${use.path}`}>
                        <Status tone="neutral">{use.source === 'draft' ? 'Draft' : 'Saved'}</Status>{' '}
                        {use.label}{' '}
                        {onShowUse && (
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => onShowUse(use)}
                          >
                            Show
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <span className="small muted">Not used by the saved book or this draft.</span>
                )}
              </div>
              <button
                type="button"
                className="small-button"
                disabled={busy || asset.in_use || !asset.sha256}
                title={asset.in_use ? 'In use: remove its uses first' : undefined}
                aria-label={`Remove ${asset.name}`}
                onClick={() => setPending({ kind: 'trash', asset })}
              >
                Remove…
              </button>
            </li>
          ))}
        </ul>
      )}
      {listing && listing.unmanaged.length > 0 && (
        <p className="small muted">
          {listing.unmanaged.length} other file(s) in cover-assets are not imported assets (for
          example {listing.unmanaged[0]}); PuzzlePress never lists or removes them. Import them to
          use them.
        </p>
      )}
      {listing && listing.trash.length > 0 && (
        <details className="asset-trash">
          <summary>Trash ({listing.trash.length})</summary>
          <ul className="asset-list compact">
            {listing.trash.map((entry) => (
              <li key={entry.trashed}>
                <div className="asset-facts">
                  <strong>{entry.restores_to.split('/').pop()}</strong>
                  <span className="small muted">
                    {entry.kind === 'photo' ? 'Photograph' : 'Font'} · {bytes(entry.bytes)}
                  </span>
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="small-button"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        'restore',
                        { trashed: entry.trashed },
                        `Restored ${entry.restores_to}.`,
                      )
                    }
                  >
                    Restore
                  </button>
                  <button
                    type="button"
                    className="small-button danger"
                    disabled={busy}
                    onClick={() => setPending({ kind: 'purge', entry })}
                  >
                    Delete permanently…
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      )}
      {blocked && blocked.uses.length > 0 && (
        <div className="notice compact-notice" role="alert">
          <p className="small">Python refused the removal; it is used by:</p>
          <ul className="small">
            {blocked.uses.map((use) => (
              <li key={`${use.source}-${use.path}`}>
                {use.label} ({use.source})
              </li>
            ))}
          </ul>
        </div>
      )}
      <p role="status" aria-live="polite" className="small">
        {message}
      </p>
      {pending && (
        <div className="dialog-backdrop">
          <div
            className="dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="asset-confirm-heading"
            aria-describedby="asset-confirm-body"
            onKeyDown={(event) => event.key === 'Escape' && setPending(null)}
          >
            {pending.kind === 'trash' ? (
              <>
                <h2 id="asset-confirm-heading">Remove {pending.asset.name}?</h2>
                <div id="asset-confirm-body">
                  <p>
                    It moves to this project&apos;s trash (cover-assets/.trash), not out of the
                    project. You can restore it later. No saved or draft design uses it.
                  </p>
                  <dl className="facts compact-facts">
                    <div>
                      <dt>File</dt>
                      <dd>{pending.asset.path}</dd>
                    </div>
                    <div>
                      <dt>Size</dt>
                      <dd>{bytes(pending.asset.bytes)}</dd>
                    </div>
                    <div>
                      <dt>SHA-256</dt>
                      <dd>
                        <code className="identity">{pending.asset.sha256}</code>
                      </dd>
                    </div>
                  </dl>
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary"
                    onClick={() =>
                      void act(
                        'trash',
                        {
                          path: pending.asset.path,
                          sha256: pending.asset.sha256,
                          revision: listing?.revision,
                          source: draft,
                        },
                        `Moved ${pending.asset.name} to the project's trash.`,
                      )
                    }
                  >
                    Move to trash
                  </button>
                  <button type="button" autoFocus onClick={() => setPending(null)}>
                    Cancel
                  </button>
                </div>
              </>
            ) : (
              <>
                <h2 id="asset-confirm-heading">
                  Delete {pending.entry.restores_to.split('/').pop()} permanently?
                </h2>
                <p id="asset-confirm-body">
                  This removes the file from the project&apos;s trash and cannot be undone. SHA-256{' '}
                  <code className="identity">{pending.entry.sha256}</code>.
                </p>
                <div className="button-row">
                  <button
                    type="button"
                    className="primary danger"
                    onClick={() =>
                      void act(
                        'purge',
                        { trashed: pending.entry.trashed, sha256: pending.entry.sha256 },
                        'Deleted permanently from the trash.',
                      )
                    }
                  >
                    Delete permanently
                  </button>
                  <button type="button" autoFocus onClick={() => setPending(null)}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
