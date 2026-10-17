import { useEffect } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./pin.css";
import { CATEGORY, type Complaint } from "../lib/complaints";
import { pinHtml, pinSize } from "../lib/pin";

// The middle of Bengaluru: places and complaints now cover the whole city, not only the north.
const BENGALURU: [number, number] = [12.98, 77.59];

/** The pin's SVG needs a real colour value, so read it from the design tokens. */
function urgencyColour(c: Complaint): string {
  const level = c.is_emergency ? 5 : Math.min(5, Math.max(1, c.urgency));
  return getComputedStyle(document.documentElement).getPropertyValue(`--urgency-${level}`).trim() || "#b45309";
}

function pinIcon(c: Complaint, selected: boolean): L.DivIcon {
  const [w, h] = pinSize(selected);
  return L.divIcon({
    className: "pin-icon",
    html: pinHtml(urgencyColour(c), c.report_count, selected),
    iconSize: [w, h],
    iconAnchor: [w / 2, h], // the point of the teardrop sits on the spot
    popupAnchor: [0, -h + 4],
  });
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
          return (
            <Marker
              key={c.tracking_id}
              position={[c.lat!, c.lon!]}
              icon={pinIcon(c, isSelected)}
              zIndexOffset={isSelected ? 1000 : c.is_emergency ? 500 : 0}
              title={`${c.tracking_id}: ${c.summary_en}`}
              alt={`${c.tracking_id}, ${CATEGORY[c.category]?.label ?? c.category}`}
              eventHandlers={{ click: () => onSelect?.(c.tracking_id) }}
            >
              <Popup>
                <strong>{c.tracking_id}</strong> · {CATEGORY[c.category]?.label ?? c.category}
                <br />
                {c.summary_en}
                <br />
                <a href={`/c/${c.tracking_id}`}>Open complaint</a>
              </Popup>
            </Marker>
          );
        })}
        <FlyTo target={target} />
      </MapContainer>
    </div>
  );
}
