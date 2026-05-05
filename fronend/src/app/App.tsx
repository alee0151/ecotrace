import { useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { router } from './routes';
import { warmIucnCache } from '../lib/api';
import 'slick-carousel/slick/slick.css';
import 'slick-carousel/slick/slick-theme.css';

export default function App() {
  useEffect(() => {
    warmIucnCache().catch((error) => {
      console.debug('IUCN cache warmup request failed', error);
    });
  }, []);

  return <RouterProvider router={router} />;
}
