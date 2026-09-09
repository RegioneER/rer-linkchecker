import {
  GET_LINKCHECKER_REPORT_PENDING,
  GET_LINKCHECKER_REPORT_SUCCESS,
  GET_LINKCHECKER_REPORT_FAIL,
} from '../constants/ActionTypes';

const initialState = {
  error: null,
  items: [],
  items_total: 0,
  summary: [],
  batching: null,
  // null means "no check has ever run", which the ui must tell apart from
  // "the last check found nothing broken": it is kept as the endpoint sends it
  last_update: null,
  duration: null,
  loading: false,
  loaded: false,
};

export default function linkchecker(state = initialState, action = {}) {
  switch (action.type) {
    case GET_LINKCHECKER_REPORT_PENDING:
      return {
        ...state,
        error: null,
        loading: true,
        loaded: false,
      };
    case GET_LINKCHECKER_REPORT_SUCCESS:
      return {
        ...state,
        error: null,
        items: action.result.items || [],
        items_total: action.result.items_total || 0,
        summary: action.result.summary || [],
        batching: action.result.batching || null,
        last_update: action.result.last_update ?? null,
        duration: action.result.duration ?? null,
        loading: false,
        loaded: true,
      };
    case GET_LINKCHECKER_REPORT_FAIL:
      return {
        ...state,
        error: action.error,
        items: [],
        items_total: 0,
        summary: [],
        batching: null,
        loading: false,
        loaded: false,
      };
    default:
      return state;
  }
}
