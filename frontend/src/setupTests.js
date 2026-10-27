// Runs before every Jest suite (Create React App picks this file up automatically).
// jsdom under Jest 27 has no TextEncoder/TextDecoder, which react-router v7 needs at import time.
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = global.TextEncoder || TextEncoder;
global.TextDecoder = global.TextDecoder || TextDecoder;

// The data cache is global to a page: every test starts without what a previous one cached.
import { clear as clearCache } from "@/lib/swr";

beforeEach(() => { clearCache(); });
