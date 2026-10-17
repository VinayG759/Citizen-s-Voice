import { useEffect } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { CATEGORY, type Complaint } from "../lib/complaints";

// The middle of Bengaluru: places and complaints now cover the whole city, not only the north.
const BENGALURU: [number, number] = [12.98, 77.59];

/** Leaflet draws on a canvas and needs real colour values, so read them from the design tokens. */
function urgencyColour(c: Complaint): string {
  const level = c.is_emergency ? 5 : Math.min(5, Math.max(1, c.urgency));
  return getComputedStyle(document.documentElement).getPropertyValue(`--urgency-${level}`).trim() || "#b45309";
}

function FlyTo({ target }: { target: Complaint | undefined }) {
  const map = useMap();
  useEffect(() => {
    if (target?.lat != null && target.lon != null) map.flyTo([target.lat, target.lon], 15, { duration: 0.8 });
  }, [map, target]);
  return null;
}

type Props = {
  complaints: Complaint[];
  selected?: string | null;
  onSelect?: (trackingId: string) => void;
  height?: number | string;
  zoom?: number;
};

export function ComplaintMap({ complaints, selected, onSelect, height = "100%", zoom = 11 }: Props) {
  const placed = complaints.filter((c) => c.lat != null && c.lon != null);
  const target = placed.find((c) => c.tracking_id === selected);
  const centre: [number, number] = placed.length === 1 ? [placed[0].lat!, placed[0].lon!] : BENGALURU;

  return (
    <div className="map" style={{ height }} role="region" aria-label="Map of complaints">
      <MapContainer center={centre} zoom={zoom} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {placed.map((c) => {
          const isSelected = c.tracking_id === selected;
          const colour = urgencyColour(c);
          return (
            <CircleMarker
              key={c.tracking_id}
              center={[c.lat!, c.lon!]}
              radius={(isSelected ? 12 : 8) + Math.min(8, (c.report_count - 1) * 2)}
              pathOptions={{ color: colour, fillColor: colour, fillOpacity: isSelected ? 0.9 : 0.6, weight: isSelected ? 3 : 1 }}
              eventHandlers={{ click: () => onSelect?.(c.tracking_id) }}
            >
              <Popup>
                <strong>{c.tracking_id}</strong> · {CATEGORY[c.category]?.label ?? c.category}
                <br />
                {c.summary_en}
                <br />
                <a href={`/c/${c.tracking_id}`}>Open complaint</a>
              </Popup>
            </CircleMarker>
          );
        })}
        <FlyTo target={target} />
      </MapContainer>
    </div>
  );
}
