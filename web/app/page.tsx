import Link from "next/link";
import styles from "./page.module.css";

const views = [
  {
    href: "/style-map",
    title: "Player style map",
    pitch: "Every player-season on a map, placed by how they play.",
  },
  {
    href: "/ask",
    title: "Ask the box score",
    pitch: "Plain-English questions answered with SQL over real stats.",
  },
  {
    href: "/shot-quality",
    title: "Shot quality court",
    pitch: "Separates good shot selection from tough shot making.",
  },
  {
    href: "/game-flow",
    title: "Game flow",
    pitch: "Win probability through every game, with the biggest swings.",
  },
];

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>NBA data hub</h1>
        <div className={styles.rule} />
        <p>Four interactive views built from stats.nba.com data.</p>
        <ul className={styles.viewList}>
          {views.map((view) => (
            <li key={view.href}>
              <Link href={view.href}>
                <strong>{view.title}</strong>
                <span>{view.pitch}</span>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
