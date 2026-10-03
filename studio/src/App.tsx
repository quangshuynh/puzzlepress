import { Component, useEffect, useRef, useState, type ReactNode } from 'react';
import { ApiError, request } from './api';
import { Library } from './Library';
import { Overview } from './Overview';
import { Inspector, PuzzleList, Quality } from './Puzzles';
import type { Generation, Project } from './types';
import { Empty, ErrorState, Loading } from './ui';

function usePath() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const update = () => setPath(window.location.pathname);
    const click = (event: MouseEvent) => {
      const link = (event.target as Element).closest('a');
      if (
        !link ||
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey ||
        link.target ||
        link.origin !== window.location.origin ||
        link.hash
      )
        return;
      event.preventDefault();
      if (link.pathname === window.location.pathname) return;
      history.pushState(null, '', link.pathname);
      update();
    };
    window.addEventListener('popstate', update);
    document.addEventListener('click', click);
    return () => {
      window.removeEventListener('popstate', update);
      document.removeEventListener('click', click);
    };
  }, []);
  return path;
}

function ProjectWorkspace({
  projectKey,
  section,
  puzzleId,
}: {
  projectKey: string;
  section: string;
  puzzleId?: string;
}) {
  const [project, setProject] = useState<Project>();
  const [error, setError] = useState<Error>();
  const [generation, setGeneration] = useState<Generation>();
  const [generationError, setGenerationError] = useState<Error>();
  const [loadingGeneration, setLoadingGeneration] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const generationController = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setError(undefined);
    request<Project>(`/api/projects/${encodeURIComponent(projectKey)}`, controller.signal)
      .then(setProject)
      .catch((err: Error) => {
        if (!controller.signal.aborted) setError(err);
      });
    return () => {
      controller.abort();
      generationController.current?.abort();
    };
  }, [projectKey, attempt]);
  const needsGeneration = section !== 'overview';
  useEffect(() => {
    if (
      !needsGeneration ||
      !project?.source?.word_search ||
      generation ||
      generationError ||
      generationController.current
    )
      return;
    const controller = new AbortController();
    generationController.current = controller;
    setLoadingGeneration(true);
    request<Generation>(
      `/api/projects/${encodeURIComponent(projectKey)}/generation`,
      controller.signal,
      { identity: project.identity },
    )
      .then((data) => {
        if (!controller.signal.aborted) setGeneration(data);
      })
      .catch((err: Error) => {
        if (!controller.signal.aborted) setGenerationError(err);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingGeneration(false);
        generationController.current = null;
      });
  }, [needsGeneration, project, projectKey, generation, generationError]);
  const retryGeneration = () => {
    setGenerationError(undefined);
    setProject(undefined);
    setAttempt((x) => x + 1);
  };
  if (error) return <ErrorState error={error} retry={() => setAttempt((x) => x + 1)} />;
  if (!project) return <Loading />;
  const base = `/books/${encodeURIComponent(projectKey)}`;
  const result = generation?.report.puzzles.find((p) => p.id === puzzleId);
  return (
    <>
      <header className="page-heading project-heading">
        <div>
          <a className="back-link" href="/books">
            Book library
          </a>
          <h1>{project.source?.book.title}</h1>
          {project.source?.book.subtitle && <p>{project.source.book.subtitle}</p>}
          <p className="muted">
            {project.source?.book.id} · {project.source?.book.language}
          </p>
        </div>
        <span className="source-note">Read-only studio</span>
      </header>
      <nav className="project-nav" aria-label="Project">
        <a href={base} aria-current={section === 'overview' ? 'page' : undefined}>
          Overview
        </a>
        <a href={`${base}/puzzles`} aria-current={section === 'puzzles' ? 'page' : undefined}>
          Puzzles <span>{project.source?.word_search?.puzzles.length ?? 0}</span>
        </a>
        <a href={`${base}/quality`} aria-current={section === 'quality' ? 'page' : undefined}>
          Quality
        </a>
      </nav>
      {section === 'overview' ? (
        <Overview project={project} />
      ) : !project.source?.word_search ? (
        <Empty title="No puzzle definitions">
          This source fixture does not configure word searches. Its authored content is available in
          Overview.
        </Empty>
      ) : generationError ? (
        <ErrorState error={generationError} retry={retryGeneration} />
      ) : loadingGeneration || !generation ? (
        <Loading>Generating and independently verifying the authored puzzles…</Loading>
      ) : section === 'quality' ? (
        <Quality generation={generation} />
      ) : puzzleId ? (
        result ? (
          <Inspector key={puzzleId} project={project} generation={generation} result={result} />
        ) : (
          <ErrorState
            error={new ApiError('This puzzle is not defined in the project.', 'puzzle_not_found')}
          />
        )
      ) : (
        <PuzzleList project={project} generation={generation} />
      )}
      {generation && (
        <footer className="analysis-footer">
          Generated analysis · pipeline {generation.report.pipeline_version} ·{' '}
          <DetailsIdentity identity={generation.report.identity} />
        </footer>
      )}
    </>
  );
}

function DetailsIdentity({ identity }: { identity: string }) {
  return (
    <details>
      <summary>Source identity</summary>
      <code className="identity">{identity}</code>
    </details>
  );
}

class RenderBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <section role="alert" className="notice error">
        <h1>Studio could not display this view</h1>
        <p>Reload the page. If this continues, check the server log.</p>
        <button onClick={() => window.location.reload()}>Reload Studio</button>
      </section>
    ) : (
      this.props.children
    );
  }
}

export function App() {
  const path = usePath();
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);
  useEffect(() => {
    document.title = 'PuzzlePress Studio';
    if (!first.current) {
      main.current?.focus();
      window.scrollTo?.(0, 0);
    }
    first.current = false;
  }, [path]);
  const match = path.match(/^\/books\/([^/]+)(?:\/(puzzles|quality)(?:\/([^/]+))?)?\/?$/);
  const isLibrary = path === '/' || path === '/books' || path === '/books/';
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="/books">
          <img src="/logo.png" alt="" />
          <span>
            PuzzlePress<small>Publishing studio</small>
          </span>
        </a>
        <nav aria-label="Library">
          <span className="nav-label">Library</span>
          <a className="nav-active" href="/books" aria-current={isLibrary ? 'page' : undefined}>
            <svg
              viewBox="0 0 24 24"
              width="20"
              height="20"
              aria-hidden="true"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <path d="M4 4h6v16H4zM14 4l5-1 3 16-5 1zM4 8h6M15 8l5-1" />
            </svg>
            Books
          </a>
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-rule" />
          <p>
            A publishing practice,
            <br />
            one puzzle at a time.
          </p>
          <small>
            Local workspace
            <br />
            Source stays on your machine
          </small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>Studio / Books</span>
          <span>Word-search workspace</span>
        </header>
        <main id="main" ref={main} tabIndex={-1}>
          <RenderBoundary>
            {isLibrary ? (
              <Library />
            ) : match && !(match[2] === 'quality' && match[3]) ? (
              <ProjectWorkspace
                key={match[1]}
                projectKey={match[1]}
                section={match[2] ?? 'overview'}
                puzzleId={match[3]}
              />
            ) : (
              <ErrorState error={new ApiError('This Studio page does not exist.', 'not_found')} />
            )}
          </RenderBoundary>
        </main>
      </div>
    </div>
  );
}
