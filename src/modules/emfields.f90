!*******************************************************************************
! Module of electromagnetic fields.
!*******************************************************************************
module emfields
    use constants, only: fp
    implicit none
    private
    public init_emfields, free_emfields, read_emfields, write_emfields
    real(fp), allocatable, dimension(:,:,:) :: ex, ey, ez, bx, by, bz, absB

    contains

    !---------------------------------------------------------------------------
    ! Initialize the fields
    !---------------------------------------------------------------------------
    subroutine init_emfields
        use topology_translate, only: ht
        implicit none
        allocate(ex(ht%nx, ht%ny, ht%nz))
        allocate(ey(ht%nx, ht%ny, ht%nz))
        allocate(ez(ht%nx, ht%ny, ht%nz))
        allocate(bx(ht%nx, ht%ny, ht%nz))
        allocate(by(ht%nx, ht%ny, ht%nz))
        allocate(bz(ht%nx, ht%ny, ht%nz))
        allocate(absB(ht%nx, ht%ny, ht%nz))

        ex = 0.0; ey = 0.0; ez = 0.0
        bx = 0.0; by = 0.0; bz = 0.0
        absB = 0.0
    end subroutine init_emfields

    !---------------------------------------------------------------------------
    ! Free the fields
    !---------------------------------------------------------------------------
    subroutine free_emfields
        implicit none
        deallocate(ex, ey, ez)
        deallocate(bx, by, bz, absB)
    end subroutine free_emfields

    !---------------------------------------------------------------------------
    ! Read electromagnetic fields from file.
    ! Inputs:
    !   tindex0: the time step index.
    !   numfold: every numfold domains are saved in one sub-directory
    !---------------------------------------------------------------------------
    subroutine read_emfields(tindex0, numfold)
        use rank_index_mapping, only: index_to_rank
        use picinfo, only: domain
        use topology_translate, only: ht
        implicit none
        integer, intent(in) :: tindex0
        integer, intent(in), optional :: numfold
        integer :: dom_x, dom_y, dom_z, n
        integer :: numfold_local
        if (.not. present(numfold)) then
            numfold_local = 1
        else
            numfold_local = numfold
        endif
        do dom_x = ht%start_x, ht%stop_x
            do dom_y = ht%start_y, ht%stop_y
                do dom_z = ht%start_z, ht%stop_z
                    call index_to_rank(dom_x, dom_y, dom_z, domain%pic_tx, &
                                       domain%pic_ty, domain%pic_tz, n)
                    call read_emfields_single(tindex0, n-1, numfold_local)
                enddo ! x
            enddo ! y
        enddo ! z
        absB = sqrt(bx**2 + by**2 + bz**2)
    end subroutine read_emfields

    !---------------------------------------------------------------------------
    ! Read the fields for a single MPI process of PIC simulation.
    ! Inputs:
    !   tindex0: the time step index.
    !   pic_mpi_id: MPI id for the PIC simulation to identify the file.
    !   numfold: every numfold domains are saved in one sub-directory
    !---------------------------------------------------------------------------
    subroutine read_emfields_single(tindex0, pic_mpi_id, numfold)
        use path_info, only: rootpath
        use constants, only: fp
        use file_header, only: read_boilerplate, read_fields_header, fheader
        use topology_translate, only: idxstart, idxstop
        use parameters, only: is_only_emf
        implicit none
        integer, intent(in) :: tindex0, pic_mpi_id, numfold
        real(fp), allocatable, dimension(:,:,:) :: buffer
        character(len=256) :: fname1, fname2
        logical :: is_exist1, is_exist2, is_exist
        integer :: fh   ! File handler
        integer :: n, ixl, iyl, izl, ixh, iyh, izh
        integer :: nc1, nc2, nc3
        integer :: tindex, folded_id

        fh = 10

        tindex = tindex0
        folded_id = pic_mpi_id / numfold
        ! Index 0 does not have proper current, so use index 1 if it exists
        if (tindex == 0) then
            write(fname1, "(A,I0,A8,I0,A1,I0)") &
                trim(adjustl(rootpath))//"fields/T.", &
                1, "/fields.", 1, ".", pic_mpi_id
            write(fname2, "(A,I0,A,I0,A8,I0,A1,I0)") &
                trim(adjustl(rootpath))//"fields/", folded_id, "/T.", &
                1, "/fields.", 1, ".", pic_mpi_id
            is_exist = .false.
            inquire(file=trim(fname1), exist=is_exist1)
            inquire(file=trim(fname2), exist=is_exist2)
            is_exist = is_exist1 .or. is_exist2
            if (is_exist) tindex = 1
        endif
        write(fname1, "(A,I0,A8,I0,A1,I0)") &
            trim(adjustl(rootpath))//"fields/T.", &
            tindex, "/fields.", tindex, ".", pic_mpi_id
        write(fname2, "(A,I0,A,I0,A8,I0,A1,I0)") &
            trim(adjustl(rootpath))//"fields/", folded_id, "/T.", &
            tindex, "/fields.", tindex, ".", pic_mpi_id
        is_exist = .false.
        inquire(file=trim(fname1), exist=is_exist1)
        inquire(file=trim(fname2), exist=is_exist2)
        is_exist = is_exist1 .or. is_exist2
      
        if (is_exist) then 
            if (is_exist1) then
                open(unit=10, file=trim(fname1), access='stream', status='unknown', &
                     form='unformatted', action='read')
            endif
            if (is_exist2) then
                open(unit=10, file=trim(fname2), access='stream', status='unknown', &
                     form='unformatted', action='read')
            endif
        else
            print *, "Can't find file: '", fname1, "' or '", fname2, "'"
            print *
            print *, " ***  Terminating ***"
            stop
        endif

        call read_boilerplate(fh)
        call read_fields_header(fh)
        allocate(buffer(fheader%nc(1), fheader%nc(2), fheader%nc(3)))     
        
        n = pic_mpi_id + 1  ! MPI ID starts at 0. The 1D rank starts at 1.
        ixl = idxstart(n, 1)
        iyl = idxstart(n, 2)
        izl = idxstart(n, 3)
        ixh = idxstop(n, 1)
        iyh = idxstop(n, 2)
        izh = idxstop(n, 3)
        nc1 = fheader%nc(1) - 1
        nc2 = fheader%nc(2) - 1
        nc3 = fheader%nc(3) - 1

        read(fh) buffer
        ex(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        read(fh) buffer
        ey(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        read(fh) buffer
        ez(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        if (is_only_emf == 0) then
            read(fh) buffer  ! Skip div_e_err
        endif
        read(fh) buffer
        bx(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        read(fh) buffer
        by(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        read(fh) buffer
        bz(ixl:ixh, iyl:iyh, izl:izh) = buffer(2:nc1, 2:nc2, 2:nc3)
        deallocate(buffer)
        close(fh)
    end subroutine read_emfields_single

    !---------------------------------------------------------------------------
    ! Save electromagnetic fields.
    !   tindex: the time step index.
    !   output_record: it decides the offset from the file head.
    !   with_suffix: whether files will have suffix
    !   suffix: indicates the kind of data
    !---------------------------------------------------------------------------
    subroutine write_emfields(tindex, output_record, with_suffix, suffix)
        use path_info, only: rootpath
        use mpi_io_translate, only: write_data
        implicit none
        integer, intent(in) :: tindex, output_record
        logical, intent(in) :: with_suffix
        character(*), intent(in) :: suffix
        if (with_suffix) then
            call write_data(trim(adjustl(rootpath))//'data/ex'//suffix, &
                            ex, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/ey'//suffix, &
                            ey, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/ez'//suffix, &
                            ez, tindex, output_record)

            call write_data(trim(adjustl(rootpath))//'data/bx'//suffix, &
                            bx, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/by'//suffix, &
                            by, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/bz'//suffix, &
                            bz, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/absB'//suffix, &
                            absB, tindex, output_record)
        else
            call write_data(trim(adjustl(rootpath))//'data/ex', &
                            ex, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/ey', &
                            ey, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/ez', &
                            ez, tindex, output_record)

            call write_data(trim(adjustl(rootpath))//'data/bx', &
                            bx, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/by', &
                            by, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/bz', &
                            bz, tindex, output_record)
            call write_data(trim(adjustl(rootpath))//'data/absB', &
                            absB, tindex, output_record)
        endif
    end subroutine write_emfields

end module emfields
