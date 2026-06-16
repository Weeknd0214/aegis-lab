import { useEffect, useState } from "react";
import { TileLayer, useMap } from "react-leaflet";

export type TileDef = {
  url: string;
  subdomains: string[];
  attribution: string;
  id: string;
};

const OSM_FALLBACK: TileDef = {
  id: "osm",
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  subdomains: ["a", "b", "c"],
  attribution: "&copy; OpenStreetMap",
};

type Props = {
  primary: TileDef;
  onActiveChange?: (tile: TileDef) => void;
};

function TileErrorWatcher({ primary, onFallback }: { primary: TileDef; onFallback: () => void }) {
  const map = useMap();
  useEffect(() => {
    let errors = 0;
    const onError = () => {
      errors += 1;
      if (errors >= 3 && primary.id !== "osm") onFallback();
    };
    map.on("tileerror", onError);
    return () => {
      map.off("tileerror", onError);
    };
  }, [map, primary.id, onFallback]);
  return null;
}

export function FallbackTileLayer({ primary, onActiveChange }: Props) {
  const [active, setActive] = useState<TileDef>(primary);

  useEffect(() => {
    setActive(primary);
  }, [primary.id, primary.url]);

  useEffect(() => {
    onActiveChange?.(active);
  }, [active, onActiveChange]);

  const fallback = () => {
    if (active.id !== "osm") setActive(OSM_FALLBACK);
  };

  return (
    <>
      <TileLayer
        key={active.id}
        attribution={active.attribution}
        url={active.url}
        subdomains={active.subdomains}
      />
      {active.id === primary.id && primary.id !== "osm" && (
        <TileErrorWatcher primary={primary} onFallback={fallback} />
      )}
    </>
  );
}
