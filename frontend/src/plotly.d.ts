// The cartesian dist bundle ships no types; @types/plotly.js describes the same API surface.
declare module 'plotly.js-cartesian-dist-min' {
  import Plotly from 'plotly.js'

  export = Plotly
}
