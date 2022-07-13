function doRepeat(fn, intervalMs) {
  fn()

  return setInterval(fn, intervalMs)
}

class Clock {
  constructor(tickMs) {
    this.tickMs = tickMs
    this.tickCount = 0
    this.repeatFns = []
    this.runOnceFns = []
    this.startSeconds = null
  }

  start() {
    this.startSeconds = Math.trunc(new Date().getTime() / 1000)

    doRepeat(() => {
      this.repeatFns.forEach(fn => fn())

      this.runOnceFns.forEach(fn => fn())
      this.runOnceFns = []

      this.tickCount += 1
    }, this.tickMs)
  }

  getTimeSeconds() {
    return this.startSeconds + (this.tickCount * this.tickMs) / 1000
  }

  onTick(fn) {
    this.repeatFns.push(fn)
  }

  onNextTick(fn) {
    this.runOnceFns.push(fn)
  }
}

function createOscilator(freq) {
  const oscillator = window.context.createOscillator()
  oscillator.type = 'sine'
  oscillator.frequency.value = freq
  oscillator.connect(window.context.destination)

  return oscillator
}

function startAlarm(freq, alarmConfig) {
  const { playSeconds, pauseSeconds, durationSeconds } = alarmConfig

  function beep() {
    const oscilator = createOscilator(freq)
    oscilator.start()

    setTimeout(() => {
      oscilator.stop()
    }, playSeconds * 1000)
  }

  const intervalId = doRepeat(beep, (playSeconds + pauseSeconds) * 1000)

  return new Promise(resolve => {
    setTimeout(() => {
      clearInterval(intervalId)

      resolve()
    }, durationSeconds * 1000)
  })
}

class AlarmManager {
  constructor(config) {
    this.baseFreq = config.baseFreq
    this.stepFreq = config.stepFreq
    this.alarmConfig = config
    this.beeping = new Set()
  }

  generateNextFreq() {
    return this.baseFreq + this.beeping.size * this.stepFreq
  }

  async startAlarm(alarmId) {
    if (this.beeping.has(alarmId)) return

    const alarmFreq = this.generateNextFreq()

    this.beeping.add(alarmId)

    await startAlarm(alarmFreq, this.alarmConfig)
    this.beeping.delete(alarmId)
  }
}

function createTimer(order, clock) {
  const endSeconds =
    Math.trunc(order.startDate.getTime() / 1000) + order.durationMinutes * 60
  const secondsLeft = endSeconds - clock.getTimeSeconds()

  const minutes = Math.trunc(secondsLeft / 60)
  const seconds = secondsLeft - minutes * 60

  const isDelayed = secondsLeft < 0
  const isExpired = minutes == 0 && seconds == 0

  return {
    minutes: minutes,
    seconds: seconds,
    isDelayed: isDelayed,
    isExpired: isExpired,
  }
}

function setUpOrder(order, clock, alarmManager) {
  const orderEl = document.createElement('div')
  orderEl.setAttribute('id', order.code)
  orderEl.classList.add('order')

  const timerEl = document.createElement('div')
  timerEl.classList.add('timer')

  const customerEl = document.createElement('div')
  customerEl.innerHTML = order.customerName

  orderEl.appendChild(customerEl)

  clock.onNextTick(() => {
    orderEl.appendChild(timerEl)
  })

  clock.onTick(() => {
    timer = createTimer(order, clock)

    if (timer.isExpired) alarmManager.startAlarm(orderEl)

    if (timer.isDelayed && timer.minutes == 0) orderEl.classList.add('expiring')
    else orderEl.classList.remove('expiring')

    timerEl.innerHTML = `${timer.minutes}:${Math.abs(timer.seconds)}`
    if (timer.isDelayed) orderEl.classList.add('expired')

    if (timer.minutes <= -order.hideAfterMinutes) orderEl.classList.add('hidden')
  })

  return orderEl
}

function updateOrderState(order, orderEl) {
  if (order.completed) orderEl.classList.add('hidden')

  if (!order.accepted) orderEl.classList.add('unaccepted')
  else orderEl.classList.remove('unaccepted')
}

function updateOrdersPage(ordersEl, orders, clock, alarmManager) {
  const orderCodes = new Set(orders.map(order => order.code))

  const existingOrderEls = document.getElementsByClassName('order')
  for (let orderEl of existingOrderEls) {
    if (!orderCodes.has(orderEl.getAttribute('id')))
      orderEl.parentElement.removeChild(orderEl)
  }

  orders.forEach(order => {
    let orderEl = document.getElementById(order.code)
    const isNewOrder = orderEl === null

    if (isNewOrder) {
      orderEl = setUpOrder(order, clock, alarmManager)
      ordersEl.appendChild(orderEl)
    }

    updateOrderState(order, orderEl)
  })
}

async function fetchOrders() {
  function fetchJson(url) {
    return fetch(url).then(res => res.json())
  }

  const [orders, manualOrders] = await Promise.all([
    fetchJson('/orders.json'),
    fetchJson('/manual_orders.json'),
  ])

  function parseOrder(order) {
    order.startDate = new Date(order.startDate)
  }

  orders.push(...manualOrders)
  orders.forEach(parseOrder)

  return orders
}

async function refreshPage(ordersEl, clock, alarmManager) {
  try {
    const deliveryOrders = await fetchOrders()

    updateOrdersPage(ordersEl, deliveryOrders, clock, alarmManager)
  } catch (error) {
    console.error(error)
  }
}

function setUpStartPage(onStart) {
  const startBtn = document.getElementById('start')

  startBtn.onclick = function () {
    const startEl = startBtn.parentElement
    startEl.parentElement.removeChild(startEl)

    window.context = new AudioContext()

    onStart()
  }
}

document.addEventListener('DOMContentLoaded', function () {
  const clock = new Clock(1000)
  clock.start()

  const alarmConfig = {
    baseFreq: 500,
    stepFreq: 28,
    playSeconds: 0.5,
    pauseSeconds: 1,
    durationSeconds: 30,
  }
  const alarmManager = new AlarmManager(alarmConfig)

  const refreshOrdersSeconds = 2

  const ordersEl = document.getElementById('orders')

  function startFrontOfHouse() {
    doRepeat(() => {
      refreshPage(ordersEl, clock, alarmManager)
    }, refreshOrdersSeconds * 1000)
  }

  setUpStartPage(startFrontOfHouse)
})
