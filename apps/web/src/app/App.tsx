import { Routes, Route, Link } from 'react-router';
import Welcome from '../screens/Welcome';
import BrandIdentity from '../screens/BrandIdentity';
import UseScreen from '../use/UseScreen';

export function App() {
  return <><header><Link to="/">Brand Copilot</Link></header><main><Routes>
    <Route path="/" element={<Welcome />} />
    <Route path="/w/:id/brand" element={<BrandIdentity />} />
    <Route path="/w/:id/use" element={<UseScreen />} />
    <Route path="*" element={<p>Page not found. <Link to="/">Go home</Link></p>} />
  </Routes></main></>;
}
