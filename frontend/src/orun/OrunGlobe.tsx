import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef, type RefObject } from 'react';
import * as THREE from 'three';
import { binaryStripTexture, oduStripTexture } from './textures';
import type { MicLevel, PulseLevel } from './audio';

const GOLD = '#d9a441';
const TEAL = '#5fc3b8';
const INK = '#eae7dc';

function Strip({
  y,
  radius,
  tube,
  texture,
  color,
  level,
}: {
  y: number;
  radius: number;
  tube: number;
  texture: THREE.CanvasTexture;
  color: string;
  level: RefObject<{ level: number } | null>;
}) {
  const ref = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshBasicMaterial>(null);

  useFrame((state) => {
    const lvl = level.current?.level ?? 0;
    const t = state.clock.elapsedTime;
    if (ref.current) {
      const jitter = Math.sin(t * 40) * lvl * 0.04;
      ref.current.position.y = y + jitter;
      const scale = 1 + lvl * 0.35;
      ref.current.scale.set(scale, scale, 1 + lvl * 1.2);
      ref.current.rotation.z += 0.0018 + lvl * 0.01;
    }
    if (mat.current) {
      mat.current.opacity = 0.55 + lvl * 0.45;
    }
  });

  return (
    <mesh ref={ref} position={[0, y, 0]} rotation={[Math.PI / 2, 0, 0]}>
      <torusGeometry args={[radius, tube, 8, 96]} />
      <meshBasicMaterial
        ref={mat}
        map={texture}
        color={color}
        transparent
        opacity={0.6}
        toneMapped={false}
      />
    </mesh>
  );
}

function InterconnectedSphere() {
  const ref = useRef<THREE.LineSegments>(null);
  const geo = useMemo(() => {
    const ico = new THREE.IcosahedronGeometry(1.55, 2);
    return new THREE.WireframeGeometry(ico);
  }, []);

  useFrame((_, delta) => {
    if (ref.current) {
      ref.current.rotation.y += delta * 0.09;
      ref.current.rotation.x += delta * 0.015;
    }
  });

  return (
    <lineSegments ref={ref} geometry={geo}>
      <lineBasicMaterial color={GOLD} transparent opacity={0.55} toneMapped={false} />
    </lineSegments>
  );
}

function EquatorLine() {
  const points = useMemo(() => {
    const pts: THREE.Vector3[] = [];
    const segs = 128;
    for (let i = 0; i <= segs; i++) {
      const a = (i / segs) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * 1.62, 0, Math.sin(a) * 1.62));
    }
    return pts;
  }, []);
  const line = useMemo(() => {
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.5, toneMapped: false });
    return new THREE.Line(geo, mat);
  }, [points]);
  return <primitive object={line} />;
}

function Glow() {
  return (
    <mesh>
      <sphereGeometry args={[1.9, 32, 32]} />
      <meshBasicMaterial color={GOLD} transparent opacity={0.035} side={THREE.BackSide} toneMapped={false} />
    </mesh>
  );
}

interface OrunGlobeProps {
  micLevel: RefObject<MicLevel | null>;
  replyLevel: RefObject<PulseLevel | null>;
  compact?: boolean;
}

export default function OrunGlobe({ micLevel, replyLevel, compact }: OrunGlobeProps) {
  const binaryTex = useMemo(() => binaryStripTexture('#d9a441'), []);
  const oduA = useMemo(() => oduStripTexture('#5fc3b8', 'single'), []);
  const oduB = useMemo(() => oduStripTexture('#5fc3b8', 'paired'), []);

  return (
    <Canvas
      camera={{ position: [0, 0.6, 4.6], fov: 42 }}
      gl={{ alpha: true, antialias: true }}
      style={{ background: 'transparent' }}
      dpr={compact ? [1, 1.5] : [1, 2]}
    >
      <ambientLight intensity={0.6} />
      <pointLight position={[3, 3, 3]} intensity={20} color={GOLD} />
      <group rotation={[0.15, 0, 0]}>
        <InterconnectedSphere />
        <EquatorLine />
        <Glow />
        <Strip y={0.34} radius={1.72} tube={0.045} texture={binaryTex} color={GOLD} level={replyLevel} />
        <Strip y={-0.3} radius={1.68} tube={0.05} texture={oduA} color={TEAL} level={micLevel} />
        <Strip y={-0.5} radius={1.6} tube={0.045} texture={oduB} color={TEAL} level={micLevel} />
      </group>
    </Canvas>
  );
}
