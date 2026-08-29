import { useEffect, useState } from 'react';
import {
  fetchEvents, addEvent, deleteEvent, fetchAlarms, addAlarm, deleteAlarm,
  fetchTasks, addTask, toggleTask, deleteTask,
  type PlannerEvent, type Alarm, type PlannerTask,
} from '../api';
import TabNav from './TabNav';
import './sections.css';
import './ogun.css';

type PlannerTab = 'tasks' | 'events' | 'alarms' | 'timers';

const TABS: { id: PlannerTab; label: string }[] = [
  { id: 'tasks', label: 'Tasks' },
  { id: 'events', label: 'Calendar' },
  { id: 'alarms', label: 'Alarms' },
  { id: 'timers', label: 'Timers' },
];

function todayStr(): string {
  return new Date().toISOString().slice(0, 10);
}

function TasksTab() {
  const [tasks, setTasks] = useState<PlannerTask[]>([]);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    fetchTasks().then(setTasks);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft('');
    const task = await addTask(text);
    setTasks((prev) => [...prev, task]);
  }

  async function toggle(t: PlannerTask) {
    setTasks((prev) => prev.map((x) => (x.id === t.id ? { ...x, completed: !x.completed } : x)));
    await toggleTask(t.id, !t.completed);
  }

  async function remove(id: string) {
    setTasks((prev) => prev.filter((t) => t.id !== id));
    await deleteTask(id);
  }

  return (
    <>
      <form className="ogun-inline-form" onSubmit={submit}>
        <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Add a to-do…" />
        <button type="submit" disabled={!draft.trim()}>Add</button>
      </form>
      <ul className="component-list planner-list">
        {tasks.map((t) => (
          <li key={t.id} className="material-row planner-row">
            <label className="planner-check">
              <input type="checkbox" checked={t.completed} onChange={() => toggle(t)} />
              <span className={t.completed ? 'done' : ''}>{t.text}</span>
            </label>
            <button className="row-remove" onClick={() => remove(t.id)} aria-label="Delete task">×</button>
          </li>
        ))}
        {tasks.length === 0 && <li className="empty">Nothing on your list yet.</li>}
      </ul>
    </>
  );
}

function EventsTab() {
  const [date, setDate] = useState(todayStr());
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const [title, setTitle] = useState('');
  const [start, setStart] = useState('09:00');
  const [end, setEnd] = useState('10:00');

  useEffect(() => {
    fetchEvents(date).then(setEvents);
  }, [date]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    const event = await addEvent(title.trim(), `${date} ${start}:00`, `${date} ${end}:00`);
    setEvents((prev) => [...prev, event].sort((a, b) => a.start_time.localeCompare(b.start_time)));
    setTitle('');
  }

  async function remove(id: string) {
    setEvents((prev) => prev.filter((e) => e.id !== id));
    await deleteEvent(id);
  }

  return (
    <>
      <form className="ogun-inline-form" onSubmit={submit}>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="ogun-small-input" />
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Event title" />
        <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className="ogun-small-input" />
        <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className="ogun-small-input" />
        <button type="submit" disabled={!title.trim()}>Add</button>
      </form>
      <ul className="component-list planner-list">
        {events.map((ev) => (
          <li key={ev.id} className="material-row planner-row">
            <div>
              <strong>{ev.title}</strong>
              <span>{ev.start_time.slice(11, 16)}–{ev.end_time.slice(11, 16)}</span>
            </div>
            <button className="row-remove" onClick={() => remove(ev.id)} aria-label="Delete event">×</button>
          </li>
        ))}
        {events.length === 0 && <li className="empty">No events on {date}.</li>}
      </ul>
    </>
  );
}

function AlarmsTab() {
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [time, setTime] = useState('07:00');
  const [label, setLabel] = useState('');

  useEffect(() => {
    fetchAlarms().then(setAlarms);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const alarm = await addAlarm(time, label.trim());
    setAlarms((prev) => [...prev, alarm].sort((a, b) => a.time.localeCompare(b.time)));
    setLabel('');
  }

  async function remove(id: string) {
    setAlarms((prev) => prev.filter((a) => a.id !== id));
    await deleteAlarm(id);
  }

  return (
    <>
      <form className="ogun-inline-form" onSubmit={submit}>
        <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className="ogun-small-input" />
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (optional)" />
        <button type="submit">Add alarm</button>
      </form>
      <ul className="component-list planner-list">
        {alarms.map((a) => (
          <li key={a.id} className="material-row planner-row">
            <div>
              <strong>{a.time}</strong>
              <span>{a.label}</span>
            </div>
            <button className="row-remove" onClick={() => remove(a.id)} aria-label="Delete alarm">×</button>
          </li>
        ))}
        {alarms.length === 0 && <li className="empty">No alarms set.</li>}
      </ul>
    </>
  );
}

interface RunningTimer {
  id: number;
  label: string;
  endsAt: number;
}

function TimersTab() {
  const [minutes, setMinutes] = useState(5);
  const [label, setLabel] = useState('');
  const [timers, setTimers] = useState<RunningTimer[]>([]);
  const [, forceTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 500);
    return () => clearInterval(id);
  }, []);

  function start(e: React.FormEvent) {
    e.preventDefault();
    if (minutes <= 0) return;
    setTimers((prev) => [...prev, { id: Date.now(), label: label.trim() || `${minutes} min timer`, endsAt: Date.now() + minutes * 60_000 }]);
    setLabel('');
  }

  function remove(id: number) {
    setTimers((prev) => prev.filter((t) => t.id !== id));
  }

  return (
    <>
      <form className="ogun-inline-form" onSubmit={start}>
        <input
          type="number" min={1} max={480} value={minutes}
          onChange={(e) => setMinutes(Number(e.target.value))} className="ogun-small-input"
        />
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label (optional)" />
        <button type="submit">Start timer</button>
      </form>
      <ul className="component-list planner-list">
        {timers.map((t) => {
          const remaining = Math.max(0, t.endsAt - Date.now());
          const mm = Math.floor(remaining / 60_000);
          const ss = Math.floor((remaining % 60_000) / 1000);
          const done = remaining <= 0;
          return (
            <li key={t.id} className="material-row planner-row">
              <div>
                <strong className={done ? 'timer-done' : ''}>{done ? 'Done!' : `${mm}:${ss.toString().padStart(2, '0')}`}</strong>
                <span>{t.label}</span>
              </div>
              <button className="row-remove" onClick={() => remove(t.id)} aria-label="Dismiss timer">×</button>
            </li>
          );
        })}
        {timers.length === 0 && <li className="empty">No timers running.</li>}
      </ul>
    </>
  );
}

export default function PlannerPanel() {
  const [tab, setTab] = useState<PlannerTab>('tasks');
  return (
    <div className="ogun-panel">
      <div className="ogun-panel-head">
        <h3>Planner</h3>
      </div>
      <TabNav tabs={TABS} active={tab} onChange={(id) => setTab(id as PlannerTab)} />
      <div className="planner-tab-body">
        {tab === 'tasks' && <TasksTab />}
        {tab === 'events' && <EventsTab />}
        {tab === 'alarms' && <AlarmsTab />}
        {tab === 'timers' && <TimersTab />}
      </div>
    </div>
  );
}
