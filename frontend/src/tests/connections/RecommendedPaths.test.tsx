/**
 * F-CONN-UX — RecommendedPaths tests.
 *
 * Coverage:
 *   1. Renders only paths whose group is in availableGroups.
 *   2. Returns nothing when no available groups.
 *   3. Click invokes onPick with the chosen group.
 *   4. activeGroup carries data-active="true".
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import RecommendedPaths from '@/components/connections/RecommendedPaths';

describe('RecommendedPaths', () => {
  it('renders only paths whose group is available', () => {
    render(
      <RecommendedPaths
        availableGroups={['start_fast', 'connect_database']}
        onPick={vi.fn()}
      />,
    );
    expect(screen.getByTestId('recommended-paths')).toBeInTheDocument();
    expect(screen.getByTestId('recommended-path-start_fast')).toBeInTheDocument();
    expect(
      screen.getByTestId('recommended-path-connect_database'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('recommended-path-enterprise_lakehouse'),
    ).not.toBeInTheDocument();
  });

  it('renders nothing when no groups are available', () => {
    const { container } = render(
      <RecommendedPaths availableGroups={[]} onPick={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('click invokes onPick with the group', () => {
    const onPick = vi.fn();
    render(
      <RecommendedPaths
        availableGroups={['start_fast', 'connect_database']}
        onPick={onPick}
      />,
    );
    fireEvent.click(screen.getByTestId('recommended-path-connect_database'));
    expect(onPick).toHaveBeenCalledWith('connect_database');
  });

  it('marks the active group with data-active=true', () => {
    render(
      <RecommendedPaths
        availableGroups={['start_fast', 'connect_database']}
        onPick={vi.fn()}
        activeGroup="connect_database"
      />,
    );
    expect(
      screen.getByTestId('recommended-path-connect_database'),
    ).toHaveAttribute('data-active', 'true');
    expect(
      screen.getByTestId('recommended-path-start_fast'),
    ).toHaveAttribute('data-active', 'false');
  });
});
