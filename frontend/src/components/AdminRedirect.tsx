import { Navigate, useParams } from 'react-router-dom';

export default function AdminRedirect() {
  const { '*': splat } = useParams();
  return <Navigate to={`/admin/${splat || ''}`} replace />;
}
