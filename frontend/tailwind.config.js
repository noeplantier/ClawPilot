/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
  	extend: {
  		borderRadius: {
  			lg: 'var(--radius)',
  			md: 'calc(var(--radius) - 2px)',
  			sm: 'calc(var(--radius) - 4px)'
  		},
  		fontFamily: {
  			sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "system-ui", "sans-serif"],
  			mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"]
  		},
  		boxShadow: {
  			glow: "0 0 32px rgba(124, 58, 237, 0.35)",
  			"glow-soft": "0 0 60px rgba(124, 58, 237, 0.18)",
  			"glow-leaf": "0 0 20px rgba(34, 197, 94, 0.3)"
  		},
  		colors: {
			void: { DEFAULT: "#07060B", elevated: "#0C0A14", surface: "#120F1E" },
			leaf: { 400: "#4ADE80", 500: "#22C55E" },
			brand: {
				50: '#F5F1FF',
				100: '#EAE1FF',
				200: '#D3C2FF',
				300: '#B79BFF',
				400: '#9B74FA',
				500: '#7C3AED',
				600: '#6D28D9',
				700: '#5B21B6',
				800: '#4C1D95',
				900: '#3B1578',
				950: '#240B4D',
			},
			"brand-violet": "var(--brand-violet)",
			"brand-violet-hover": "var(--brand-violet-hover)",
			"brand-lilac": "var(--brand-lilac)",
  			background: 'hsl(var(--background))',
  			foreground: 'hsl(var(--foreground))',
  			card: {
  				DEFAULT: 'hsl(var(--card))',
  				foreground: 'hsl(var(--card-foreground))'
  			},
  			popover: {
  				DEFAULT: 'hsl(var(--popover))',
  				foreground: 'hsl(var(--popover-foreground))'
  			},
  			primary: {
  				DEFAULT: 'hsl(var(--primary))',
  				foreground: 'hsl(var(--primary-foreground))'
  			},
  			secondary: {
  				DEFAULT: 'hsl(var(--secondary))',
  				foreground: 'hsl(var(--secondary-foreground))'
  			},
  			muted: {
  				DEFAULT: 'hsl(var(--muted))',
  				foreground: 'hsl(var(--muted-foreground))'
  			},
  			accent: {
  				DEFAULT: 'hsl(var(--accent))',
  				foreground: 'hsl(var(--accent-foreground))'
  			},
  			destructive: {
  				DEFAULT: 'hsl(var(--destructive))',
  				foreground: 'hsl(var(--destructive-foreground))'
  			},
  			border: 'hsl(var(--border))',
  			input: 'hsl(var(--input))',
  			ring: 'hsl(var(--ring))',
  			chart: {
  				'1': 'hsl(var(--chart-1))',
  				'2': 'hsl(var(--chart-2))',
  				'3': 'hsl(var(--chart-3))',
  				'4': 'hsl(var(--chart-4))',
  				'5': 'hsl(var(--chart-5))'
  			}
  		},
  		keyframes: {
  			'accordion-down': {
  				from: {
  					height: '0'
  				},
  				to: {
  					height: 'var(--radix-accordion-content-height)'
  				}
  			},
  			'accordion-up': {
  				from: {
  					height: 'var(--radix-accordion-content-height)'
  				},
  				to: {
  					height: '0'
  				}
  			}
  		},
  		animation: {
  			'accordion-down': 'accordion-down 0.2s ease-out',
  			'accordion-up': 'accordion-up 0.2s ease-out'
  		}
  	}
  },
  plugins: [require("tailwindcss-animate")],
};
