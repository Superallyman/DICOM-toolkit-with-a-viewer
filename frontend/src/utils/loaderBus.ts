// src/utils/loaderBus.ts
type Listener = (count: number) => void;

class LoaderBus {
  private count = 0;
  private listeners = new Set<Listener>();

  getCount() {
    return this.count;
  }

  inc() {
    this.count += 1;
    this.emit();
  }

  dec() {
    if (this.count > 0) this.count -= 1;
    this.emit();
  }

  clear() {
    this.count = 0;
    this.emit();
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn);
    // push current value to new subscribers
    fn(this.count);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    this.listeners.forEach((fn) => fn(this.count));
  }
}

export const loaderBus = new LoaderBus();
