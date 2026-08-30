import { Navigate, useParams, useLocation } from 'react-router-dom';

interface Props {
  base: string;
  suffix?: string;
}

export default function WorkspaceRedirect({ base, suffix }: Props) {
  const { id, '*': splat } = useParams();
  const location = useLocation();
  let target = `${base}/${id}`;
  if (suffix) target += suffix;
  if (splat) target += `/${splat}`;
  return <Navigate to={`${target}${location.search}`} replace />;
}
