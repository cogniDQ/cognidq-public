import React from 'react';

interface HeatMapProps {
  data: Array<{
    x: string;
    y: string;
    value: number;
  }>;
  title?: string;
  colorScale?: {
    min: string;
    mid: string;
    max: string;
  };
}

export const HeatMap: React.FC<HeatMapProps> = ({
  data,
  title,
  colorScale = { min: '#10B981', mid: '#F59E0B', max: '#EF4444' },
}) => {
  // Get unique x and y values
  const xValues = Array.from(new Set(data.map((d) => d.x)));
  const yValues = Array.from(new Set(data.map((d) => d.y)));

  // Find min and max values for color scaling
  const values = data.map((d) => d.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);

  const getColor = (value: number) => {
    const normalized = (value - minValue) / (maxValue - minValue);
    if (normalized < 0.5) {
      return colorScale.min;
    } else if (normalized < 0.75) {
      return colorScale.mid;
    } else {
      return colorScale.max;
    }
  };

  const getValue = (x: string, y: string) => {
    const item = data.find((d) => d.x === x && d.y === y);
    return item?.value ?? 0;
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      {title && <h3 className="text-lg font-semibold text-white mb-4">{title}</h3>}
      <div className="overflow-x-auto">
        <table className="border-collapse">
          <thead>
            <tr>
              <th className="p-2"></th>
              {xValues.map((x) => (
                <th key={x} className="p-2 text-xs text-gray-400 font-medium">
                  {x}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {yValues.map((y) => (
              <tr key={y}>
                <td className="p-2 text-xs text-gray-400 font-medium">{y}</td>
                {xValues.map((x) => {
                  const value = getValue(x, y);
                  return (
                    <td
                      key={`${x}-${y}`}
                      className="p-2 text-center text-xs font-medium text-white border border-gray-700"
                      style={{
                        backgroundColor: getColor(value),
                        minWidth: '50px',
                        minHeight: '50px',
                      }}
                      title={`${x} × ${y}: ${value}`}
                    >
                      {value}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex items-center gap-4 text-xs text-gray-400">
        <span>Low</span>
        <div className="flex gap-1">
          <div className="w-8 h-4" style={{ backgroundColor: colorScale.min }}></div>
          <div className="w-8 h-4" style={{ backgroundColor: colorScale.mid }}></div>
          <div className="w-8 h-4" style={{ backgroundColor: colorScale.max }}></div>
        </div>
        <span>High</span>
      </div>
    </div>
  );
};
