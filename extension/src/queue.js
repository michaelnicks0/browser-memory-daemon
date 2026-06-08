class MemoryQueue {
  constructor(items = []) {
    this.items = Array.from(items);
  }

  enqueue(item) {
    this.items.push({ ...item, queued_at: new Date().toISOString() });
    return this.items.length;
  }

  peek() {
    return this.items[0] || null;
  }

  shift() {
    return this.items.shift() || null;
  }

  size() {
    return this.items.length;
  }
}

if (typeof module !== 'undefined') {
  module.exports = { MemoryQueue };
}
