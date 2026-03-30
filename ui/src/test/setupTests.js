import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";

const hasWindow = typeof window !== "undefined";
const originalLocation = hasWindow ? window.location : undefined;
const originalTextEncoder = globalThis.TextEncoder;
const originalTextDecoder = globalThis.TextDecoder;
const originalUint8Array = globalThis.Uint8Array;

const passthroughWarn = console.warn.bind(console);
const passthroughError = console.error.bind(console);

console.warn = (...args) => {
	const message = args.map(String).join(" ");
	if (message.includes("React Router Future Flag Warning")) {
		return;
	}
	passthroughWarn(...args);
};

console.error = (...args) => {
	const message = args.map(String).join(" ");
	if (
		message.includes("not wrapped in act(...)") ||
		message.includes("Not implemented: navigation (except hash changes)") ||
		message.includes("A component is changing a controlled input to be uncontrolled")
	) {
		return;
	}
	passthroughError(...args);
};

afterEach(() => {
	if (hasWindow && window.location !== originalLocation) {
		Object.defineProperty(window, "location", {
			configurable: true,
			value: originalLocation,
			writable: true,
		});
	}

	if (globalThis.TextEncoder !== originalTextEncoder) {
		globalThis.TextEncoder = originalTextEncoder;
	}
	if (globalThis.TextDecoder !== originalTextDecoder) {
		globalThis.TextDecoder = originalTextDecoder;
	}
	if (globalThis.Uint8Array !== originalUint8Array) {
		globalThis.Uint8Array = originalUint8Array;
	}
});
