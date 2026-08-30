import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';

interface ExecutionData {
  id: string;
  flow_name?: string;
  status: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  updated_at?: string;
  nodes_executed: number;
  nodes_passed: number;
  nodes_failed: number;
  nodes_skipped: number;
  result_summary?: any;
  error_message?: string;
}

interface NodeResult {
  node_type: string;
  status: string;
  result_data?: any;
}

export async function generateExecutionReportPDF(
  execution: ExecutionData,
  nodeResults: NodeResult[],
  flowName: string
) {
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  let yPosition = 20;

  // Colors
  const successColor = [34, 197, 94]; // Green
  const errorColor = [239, 68, 68]; // Red
  const grayColor = [156, 163, 175];
  const darkGray = [75, 85, 99];

  // ===== HEADER WITH GRADIENT EFFECT =====
  // Blue gradient background
  doc.setFillColor(37, 99, 235);
  doc.rect(0, 0, pageWidth, 45, 'F');
  doc.setFillColor(147, 51, 234);
  doc.rect(pageWidth * 0.6, 0, pageWidth * 0.4, 45, 'F');

  // Title
  doc.setTextColor(255, 255, 255);
  doc.setFontSize(24);
  doc.setFont('helvetica', 'bold');
  doc.text('Data Quality Execution Report', pageWidth / 2, 20, { align: 'center' });

  // Subtitle
  doc.setFontSize(11);
  doc.setFont('helvetica', 'normal');
  doc.text(`Flow: ${flowName || 'Unnamed Flow'}`, pageWidth / 2, 30, { align: 'center' });
  doc.text(`Generated: ${new Date().toLocaleString()}`, pageWidth / 2, 37, { align: 'center' });

  yPosition = 55;

  // ===== EXECUTION SUMMARY BOX =====
  doc.setDrawColor(...grayColor);
  doc.setFillColor(249, 250, 251);
  doc.roundedRect(15, yPosition, pageWidth - 30, 35, 3, 3, 'FD');

  doc.setTextColor(...darkGray);
  doc.setFontSize(10);
  doc.setFont('helvetica', 'bold');

  // Run ID
  doc.text('Run ID:', 20, yPosition + 8);
  doc.setFont('helvetica', 'normal');
  doc.text(execution.id.slice(0, 8), 40, yPosition + 8);

  // Status
  doc.setFont('helvetica', 'bold');
  doc.text('Status:', 20, yPosition + 16);
  const statusColor = execution.status === 'completed' ? successColor : 
                      execution.status === 'failed' ? errorColor : grayColor;
  doc.setTextColor(...statusColor);
  doc.text(execution.status.toUpperCase(), 40, yPosition + 16);
  doc.setTextColor(...darkGray);

  // Started At
  doc.setFont('helvetica', 'bold');
  doc.text('Started:', 20, yPosition + 24);
  doc.setFont('helvetica', 'normal');
  doc.text(new Date(execution.created_at).toLocaleString(), 40, yPosition + 24);

  // Duration
  const duration = calculateDuration(execution);
  doc.setFont('helvetica', 'bold');
  doc.text('Duration:', 120, yPosition + 8);
  doc.setFont('helvetica', 'normal');
  doc.text(duration, 145, yPosition + 8);

  // Trigger
  doc.setFont('helvetica', 'bold');
  doc.text('Triggered By:', 120, yPosition + 16);
  doc.setFont('helvetica', 'normal');
  doc.text('Manual Execution', 145, yPosition + 16);

  yPosition += 45;

  // ===== DATASETS INVOLVED =====
  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(...darkGray);
  doc.text('📦 Datasets Involved', 15, yPosition);
  yPosition += 8;

  const sourceNodes = nodeResults.filter(n => n.node_type === 'source');
  const datasetsData = sourceNodes.map(node => {
    const rowCount = getRowCount(node, nodeResults, execution);
    return [
      node.result_data?.table_name || node.result_data?.dataset || 'Unknown',
      `${node.result_data?.data_source?.type || 'PostgreSQL'} - ${node.result_data?.schema_name || 'Production'}`,
      rowCount,
      node.status === 'completed' ? 'Success' : node.status
    ];
  });

  if (datasetsData.length === 0) {
    const rowCount = getRowCountFromExecution(nodeResults, execution);
    datasetsData.push([
      flowName || 'Dataset',
      'PostgreSQL - Production',
      rowCount,
      'Success'
    ]);
  }

  autoTable(doc, {
    startY: yPosition,
    head: [['Dataset', 'Source', 'Rows Analyzed', 'Status']],
    body: datasetsData,
    theme: 'grid',
    headStyles: {
      fillColor: darkGray,
      textColor: [255, 255, 255],
      fontSize: 10,
      fontStyle: 'bold'
    },
    bodyStyles: {
      fontSize: 9,
      textColor: darkGray
    },
    alternateRowStyles: {
      fillColor: [249, 250, 251]
    },
    margin: { left: 15, right: 15 }
  });

  yPosition = (doc as any).lastAutoTable.finalY + 15;

  // ===== RUN-LEVEL METRICS =====
  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.text('📊 Run-Level Metrics', 15, yPosition);
  yPosition += 10;

  const metrics = [
    { label: 'Total Checks', value: execution.nodes_executed || 0, color: grayColor },
    { label: 'Passed', value: execution.nodes_passed || 0, color: successColor },
    { label: 'Warnings', value: 0, color: [251, 191, 36] },
    { label: 'Failed', value: execution.nodes_failed || 0, color: errorColor },
    { label: 'Skipped', value: execution.nodes_skipped || 0, color: grayColor },
    { 
      label: 'Pass Rate', 
      value: execution.nodes_executed > 0 
        ? Math.round((execution.nodes_passed / execution.nodes_executed) * 100) + '%'
        : '0%',
      color: grayColor 
    }
  ];

  const boxWidth = 30;
  const boxHeight = 25;
  const spacing = 3;
  const startX = 15;

  metrics.forEach((metric, idx) => {
    const x = startX + (idx * (boxWidth + spacing));
    
    // Box
    doc.setDrawColor(...grayColor);
    doc.setFillColor(249, 250, 251);
    doc.roundedRect(x, yPosition, boxWidth, boxHeight, 2, 2, 'FD');
    
    // Label
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...grayColor);
    doc.text(metric.label, x + boxWidth / 2, yPosition + 7, { align: 'center' });
    
    // Value
    doc.setFontSize(16);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...metric.color);
    doc.text(String(metric.value), x + boxWidth / 2, yPosition + 18, { align: 'center' });
  });

  yPosition += boxHeight + 15;

  // ===== CHECKS APPLIED =====
  if (yPosition > pageHeight - 60) {
    doc.addPage();
    yPosition = 20;
  }

  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.setTextColor(...darkGray);
  doc.text('✅ Checks Applied', 15, yPosition);
  yPosition += 8;

  const checkNodes = nodeResults.filter(n => n.node_type === 'check');

  if (checkNodes.length > 0) {
    checkNodes.forEach((checkNode) => {
      if (yPosition > pageHeight - 50) {
        doc.addPage();
        yPosition = 20;
      }

      // Check box
      doc.setDrawColor(...grayColor);
      doc.setFillColor(249, 250, 251);
      doc.roundedRect(15, yPosition, pageWidth - 30, 30, 3, 3, 'FD');

      // Check type and status
      doc.setFontSize(11);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(...darkGray);
      const checkType = checkNode.result_data?.check_type || 'Data Quality Check';
      doc.text(checkType.charAt(0).toUpperCase() + checkType.slice(1), 20, yPosition + 8);

      // Status badge
      const checkStatusColor = checkNode.status === 'completed' ? successColor : errorColor;
      doc.setFillColor(...checkStatusColor);
      doc.roundedRect(pageWidth - 45, yPosition + 3, 25, 7, 2, 2, 'F');
      doc.setFontSize(8);
      doc.setTextColor(255, 255, 255);
      doc.setFont('helvetica', 'bold');
      doc.text(checkNode.status === 'completed' ? 'PASSED' : 'FAILED', pageWidth - 32.5, yPosition + 8, { align: 'center' });

      // Columns
      doc.setFontSize(9);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(...grayColor);
      const columns = checkNode.result_data?.columns?.join(', ') || 'No columns specified';
      doc.text(`Columns: ${columns}`, 20, yPosition + 14);

      // Metrics
      const rowsChecked = checkNode.result_data?.rows_scanned || checkNode.result_data?.total_rows || 0;
      const validRows = checkNode.result_data?.rows_passed || checkNode.result_data?.valid_rows || 0;
      const invalidRows = checkNode.result_data?.rows_failed || checkNode.result_data?.invalid_rows || 0;

      doc.setTextColor(...darkGray);
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8);
      doc.text('Rows Checked', 20, yPosition + 20);
      doc.text('Valid Rows', 70, yPosition + 20);
      doc.text('Invalid Rows', 120, yPosition + 20);

      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');
      doc.text(rowsChecked.toLocaleString(), 20, yPosition + 26);
      doc.setTextColor(...successColor);
      doc.text(validRows.toLocaleString(), 70, yPosition + 26);
      doc.setTextColor(...errorColor);
      doc.text(invalidRows.toLocaleString(), 120, yPosition + 26);

      yPosition += 35;
    });
  } else {
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...grayColor);
    doc.text('No check nodes found in this execution.', 20, yPosition + 10);
    yPosition += 20;
  }

  // ===== ERROR DETAILS =====
  if (execution.error_message) {
    if (yPosition > pageHeight - 40) {
      doc.addPage();
      yPosition = 20;
    }

    doc.setFontSize(14);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(...darkGray);
    doc.text('⚠️ Error Details', 15, yPosition);
    yPosition += 8;

    doc.setDrawColor(...errorColor);
    doc.setFillColor(254, 242, 242);
    doc.roundedRect(15, yPosition, pageWidth - 30, 25, 3, 3, 'FD');

    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...errorColor);
    const errorLines = doc.splitTextToSize(execution.error_message, pageWidth - 40);
    doc.text(errorLines, 20, yPosition + 8);
  }

  // ===== FOOTER =====
  const totalPages = doc.getNumberOfPages();
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(...grayColor);
    doc.text(
      `Page ${i} of ${totalPages} | CogniDQ Platform | Confidential`,
      pageWidth / 2,
      pageHeight - 10,
      { align: 'center' }
    );
  }

  // Save the PDF
  const fileName = `DQ_Report_${execution.id.slice(0, 8)}_${new Date().toISOString().split('T')[0]}.pdf`;
  doc.save(fileName);
}

function calculateDuration(execution: ExecutionData): string {
  if (execution.result_summary?.execution_time) {
    const seconds = Math.floor(execution.result_summary.execution_time);
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }
  if (execution.started_at && execution.completed_at) {
    const duration = Math.floor(
      (new Date(execution.completed_at).getTime() - new Date(execution.started_at).getTime()) / 1000
    );
    return `${Math.floor(duration / 60)}m ${duration % 60}s`;
  }
  if (execution.created_at && execution.updated_at) {
    const duration = Math.floor(
      (new Date(execution.updated_at).getTime() - new Date(execution.created_at).getTime()) / 1000
    );
    return `${Math.floor(duration / 60)}m ${duration % 60}s`;
  }
  return 'N/A';
}

function getRowCount(sourceNode: NodeResult, allNodes: NodeResult[], execution: ExecutionData): string {
  const rowCount = sourceNode.result_data?.row_count || 
                  sourceNode.result_data?.rows_scanned || 
                  sourceNode.result_data?.total_rows ||
                  sourceNode.result_data?.output_data?.row_count;
  
  if (!rowCount || rowCount === 0) {
    const checkNode = allNodes.find(n => n.node_type === 'check');
    if (checkNode?.result_data?.rows_scanned) {
      return checkNode.result_data.rows_scanned.toLocaleString();
    }
    if (execution.result_summary?.total_rows_scanned) {
      return execution.result_summary.total_rows_scanned.toLocaleString();
    }
  }
  
  return rowCount ? rowCount.toLocaleString() : '0';
}

function getRowCountFromExecution(allNodes: NodeResult[], execution: ExecutionData): string {
  if (execution.result_summary?.total_rows_scanned) {
    return execution.result_summary.total_rows_scanned.toLocaleString();
  }
  const checkNode = allNodes.find(n => n.node_type === 'check');
  if (checkNode?.result_data?.rows_scanned) {
    return checkNode.result_data.rows_scanned.toLocaleString();
  }
  return '0';
}
