import React from 'react'
import { fireEvent, render } from '@testing-library/react'
import RCAPage from '../RCAPage'

const createJobMock = vi.fn(async () => ({ job_id: 'job-1', status: 'queued' }))
const refreshJobsMock = vi.fn()
const setSelectedJobIdMock = vi.fn()
const reloadReportMock = vi.fn()

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'u1' },
  }),
}))

vi.mock('../../hooks/useRcaJobs', () => ({
  useRcaJobs: () => ({
    jobs: [],
    loadingJobs: false,
    creatingJob: false,
    deletingReport: false,
    selectedJobId: null,
    selectedJob: null,
    setSelectedJobId: setSelectedJobIdMock,
    createJob: createJobMock,
    deleteReportById: vi.fn(),
    removeJobByReportId: vi.fn(),
    refreshJobs: refreshJobsMock,
  }),
}))

vi.mock('../../hooks/useRcaReport', () => ({
  useRcaReport: () => ({
    loadingReport: false,
    reportError: null,
    report: null,
    reportMeta: null,
    insights: {},
    hasReport: false,
    reloadReport: reloadReportMock,
  }),
}))

describe('RCAPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('submits a create job request from composer', () => {
    const { getByText } = render(<RCAPage />)
    fireEvent.click(getByText('Generate Report'))
    expect(createJobMock).toHaveBeenCalledTimes(1)
    const payload = createJobMock.mock.calls[0][0]
    expect(payload).toHaveProperty('start')
    expect(payload).toHaveProperty('end')
    expect(payload).toHaveProperty('sensitivity')
  })

  it('shows quick-stat tiles when a report is available', () => {
    // override report hook to provide a fake report
    const fakeReport = {
      summary: 'Test summary',
      overall_severity: 'high',
      metric_anomalies: [1, 2],
      root_causes: [1],
      duration_seconds: 42,
    }
    vi.mock('../../hooks/useRcaReport', () => ({
      useRcaReport: () => ({
        loadingReport: false,
        reportError: null,
        report: fakeReport,
        reportMeta: fakeReport,
        insights: {},
        hasReport: true,
        reloadReport: reloadReportMock,
      }),
    }))

    const { queryByText, getByText } = render(<RCAPage />)
    // summary paragraph should no longer be rendered at top
    expect(queryByText('Test summary')).not.toBeInTheDocument()
    // metrics should render as cards
    expect(getByText('Overall Severity')).toBeInTheDocument()
    expect(getByText('HIGH')).toBeInTheDocument()
    expect(getByText('Metric Anomalies')).toBeInTheDocument()
    expect(getByText('2')).toBeInTheDocument()
    expect(getByText('Root Causes')).toBeInTheDocument()
    expect(getByText('1')).toBeInTheDocument()
    expect(getByText('Duration (s)')).toBeInTheDocument()
    expect(getByText('42')).toBeInTheDocument()
  })

  it('restores selected job id from localStorage when jobs include it', () => {
    localStorage.setItem('rcaPage.selectedJobId', 'stored-job')
    // provide jobs that include the stored id
    vi.mock('../../hooks/useRcaJobs', () => ({
      useRcaJobs: () => ({
        jobs: [{ job_id: 'stored-job' }],
        loadingJobs: false,
        creatingJob: false,
        deletingReport: false,
        selectedJobId: null,
        selectedJob: null,
        setSelectedJobId: setSelectedJobIdMock,
        createJob: createJobMock,
        deleteReportById: vi.fn(),
        removeJobByReportId: vi.fn(),
        refreshJobs: refreshJobsMock,
      }),
    }))

    render(<RCAPage />)
    expect(setSelectedJobIdMock).toHaveBeenCalledWith('stored-job')
  })
})
