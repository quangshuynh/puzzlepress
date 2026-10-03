import { createRoot } from 'react-dom/client';
import '@fontsource-variable/newsreader';
import '@fontsource-variable/public-sans';
import './style.css';
import { App } from './App';

createRoot(document.getElementById('root')!).render(<App />);
